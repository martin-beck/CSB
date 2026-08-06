# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

import csv
import os
import re
from collections import defaultdict
from pathlib import Path

import bm_config
from bm_utils import resolve_path
from monitors.monitor import Monitor
from utils.logger import LogType, bm_log
from utils.process import BackgroundProcess


class SchedulerScalability(Monitor):
    """Collect wakeup placement, migration, latency, and preemption evidence."""

    PROGRAM = "scripts/bpftrace/bpf_sched_scalability.bt"
    RAW_FILE = "scheduler-scalability-raw.txt"
    ERROR_FILE = "scheduler-scalability.err"
    MATRIX_FILE = "scheduler-placement-matrix.csv"
    EVENT_PATTERN = re.compile(
        r"^CSB_SCHED\|(?P<pid>\d+)\|(?P<comm>[^|]*)\|(?P<previous_cpu>-?\d+)\|"
        r"(?P<target_cpu>-?\d+)\|(?P<run_cpu>\d+)\|(?P<latency_ns>\d+)$",
        re.MULTILINE,
    )
    PREEMPT_PATTERN = re.compile(r"^CSB_SCHED_PREEMPTIONS\|(\d+)$", re.MULTILINE)
    LOST_PATTERN = re.compile(r"(?:lost|dropped)\D+(\d+)\D+events?", re.IGNORECASE)
    MATRIX_HEADER = [
        "previous_cpu",
        "target_cpu",
        "run_cpu",
        "count",
        "migrations",
        "target_misses",
        "total_latency_ns",
        "p50_latency_ns",
        "p95_latency_ns",
        "p99_latency_ns",
        "max_latency_ns",
    ]

    def __init__(self, output_dir: str, args: list[str] = []):
        super().__init__(dir=output_dir, args=args)
        self.name = "scheduler-scalability"
        target = args[0] if args else self._application_name()
        program = self.program_for_target(target[:15])
        self.trace = BackgroundProcess(
            name=self.name,
            ofile_name=self.RAW_FILE,
            efile_name=self.ERROR_FILE,
            cmds=["sudo", "bpftrace", "-e", program],
            out_dir=output_dir,
            requires=["bpftrace"],
            pin=self.get_cpus(),
        )

    def start(self):
        self.trace.start()
        if not self.trace.await_token("Attaching"):
            bm_log("scheduler monitor could not confirm probe attachment", LogType.ERROR)

    def stop(self):
        if self.trace.stop() != 0:
            bm_log("scheduler bpftrace process failed; inspect its stderr", LogType.ERROR)

    def collect_results(self) -> str:
        content = self.trace.read_output()
        events = self.parse_events(content)
        matrix = self.aggregate_matrix(events)
        self.write_matrix(matrix, os.path.join(self.dir, self.MATRIX_FILE))
        latencies = [event["latency_ns"] for event in events]
        migrations = sum(self.is_migration(event) for event in events)
        target_misses = sum(event["target_cpu"] != event["run_cpu"] for event in events)
        lost = self.parse_lost_events(self._read_errors())
        return (
            f"scheduler_wakeups={len(events)};"
            f"scheduler_migrations={migrations};"
            f"scheduler_target_misses={target_misses};"
            f"scheduler_latency_p95_ns={self.percentile(latencies, 95)};"
            f"scheduler_preemptions={self.parse_preemptions(content)};"
            f"scheduler_lost_events={lost};"
        )

    @classmethod
    def parse_events(cls, content: str) -> list[dict]:
        events = []
        for match in cls.EVENT_PATTERN.finditer(content):
            event = match.groupdict()
            for field in ("pid", "previous_cpu", "target_cpu", "run_cpu", "latency_ns"):
                event[field] = int(event[field])
            events.append(event)
        return events

    @classmethod
    def aggregate_matrix(cls, events: list[dict]) -> list[dict]:
        groups = defaultdict(list)
        for event in events:
            groups[(event["previous_cpu"], event["target_cpu"], event["run_cpu"])].append(event)
        rows = []
        for (previous_cpu, target_cpu, run_cpu), group in groups.items():
            latencies = [event["latency_ns"] for event in group]
            rows.append(
                {
                    "previous_cpu": previous_cpu,
                    "target_cpu": target_cpu,
                    "run_cpu": run_cpu,
                    "count": len(group),
                    "migrations": sum(cls.is_migration(event) for event in group),
                    "target_misses": sum(
                        event["target_cpu"] != event["run_cpu"] for event in group
                    ),
                    "total_latency_ns": sum(latencies),
                    "p50_latency_ns": cls.percentile(latencies, 50),
                    "p95_latency_ns": cls.percentile(latencies, 95),
                    "p99_latency_ns": cls.percentile(latencies, 99),
                    "max_latency_ns": max(latencies),
                }
            )
        return sorted(rows, key=lambda row: row["total_latency_ns"], reverse=True)

    @staticmethod
    def is_migration(event: dict) -> bool:
        return event["previous_cpu"] >= 0 and event["previous_cpu"] != event["run_cpu"]

    @staticmethod
    def percentile(values: list[int], percentile: int) -> int:
        if not values:
            return 0
        ordered = sorted(values)
        return ordered[max(0, (len(ordered) * percentile + 99) // 100 - 1)]

    @classmethod
    def parse_preemptions(cls, content: str) -> int:
        matches = cls.PREEMPT_PATTERN.findall(content)
        return int(matches[-1]) if matches else 0

    @classmethod
    def parse_lost_events(cls, content: str) -> int:
        return sum(int(match) for match in cls.LOST_PATTERN.findall(content))

    @classmethod
    def write_matrix(cls, rows: list[dict], path: str):
        with open(path, "w", newline="", encoding="utf-8") as output:
            writer = csv.DictWriter(output, fieldnames=cls.MATRIX_HEADER)
            writer.writeheader()
            writer.writerows(rows)

    @classmethod
    def program_for_target(cls, target: str) -> str:
        if not target or any(character in target for character in ('"', "\\", "\n")):
            raise ValueError("scheduler target comm must be a non-empty literal")
        return Path(resolve_path(cls.PROGRAM)).read_text().replace("__TARGET_COMM__", target)

    def _read_errors(self) -> str:
        try:
            return Path(self.trace.err_file_name).read_text(encoding="utf-8")
        except OSError as error:
            bm_log(f"Could not read scheduler monitor errors: {error}", LogType.ERROR)
            return ""

    @staticmethod
    def _application_name() -> str:
        if bm_config.g_config is None or len(bm_config.g_config.get_apps()) != 1:
            raise ValueError("scheduler monitor requires exactly one application")
        return bm_config.g_config.get_apps()[0].name
