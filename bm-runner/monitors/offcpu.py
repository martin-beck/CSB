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


class OffCpu(Monitor):
    """Collect complete sleeper-stack to waker-stack off-CPU edges."""

    PROGRAM = "scripts/bpftrace/bpf_offcpu_matrix.bt"
    RAW_FILE = "offcpu-raw.txt"
    ERROR_FILE = "offcpu.err"
    MATRIX_FILE = "offcpu-matrix.csv"
    EVENT_PATTERN = re.compile(
        r"CSB_OFFCPU_BEGIN\|(?P<sleeper_pid>\d+)\|(?P<sleeper_comm>[^|]*)\|"
        r"(?P<waker_pid>\d+)\|(?P<waker_comm>[^|]*)\|(?P<offcpu_ns>\d+)\|"
        r"(?P<sleep_ns>\d+)\|(?P<runq_ns>\d+)\n(?P<sleeper_stack>.*?)\n"
        r"CSB_WAKER_STACK\n(?P<waker_stack>.*?)\nCSB_OFFCPU_END",
        re.DOTALL,
    )
    LOST_PATTERN = re.compile(r"(?:lost|dropped)\D+(\d+)\D+events?", re.IGNORECASE)
    MATRIX_HEADER = [
        "sleeper_comm",
        "waker_comm",
        "sleeper_stack",
        "waker_stack",
        "count",
        "total_offcpu_ns",
        "total_sleep_ns",
        "total_runq_ns",
        "p50_offcpu_ns",
        "p95_offcpu_ns",
        "p99_offcpu_ns",
        "max_offcpu_ns",
    ]

    def __init__(self, output_dir: str, args: list[str] = []):
        super().__init__(dir=output_dir, args=args)
        self.name = "offcpu"
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
            bm_log("offcpu could not confirm that probes attached", LogType.ERROR)

    def stop(self):
        if self.trace.stop() != 0:
            bm_log("offcpu bpftrace process failed; inspect offcpu.err", LogType.ERROR)

    def collect_results(self) -> str:
        events = self.parse_events(self.trace.read_output())
        matrix = self.aggregate_matrix(events)
        self.write_matrix(matrix, os.path.join(self.dir, self.MATRIX_FILE))
        lost = self.parse_lost_events(self._read_errors())
        if lost:
            bm_log(f"offcpu lost or dropped {lost} events", LogType.ERROR)
        offcpu = [event["offcpu_ns"] for event in events]
        runq = [event["runq_ns"] for event in events]
        return (
            f"offcpu_events={len(events)};"
            f"offcpu_matrix_edges={len(matrix)};"
            f"offcpu_total_ns={sum(offcpu)};"
            f"offcpu_p95_ns={self.percentile(offcpu, 95)};"
            f"offcpu_runq_p95_ns={self.percentile(runq, 95)};"
            f"offcpu_lost_events={lost};"
        )

    @classmethod
    def parse_events(cls, content: str) -> list[dict]:
        events = []
        for match in cls.EVENT_PATTERN.finditer(content):
            event = match.groupdict()
            for field in ("sleeper_pid", "waker_pid", "offcpu_ns", "sleep_ns", "runq_ns"):
                event[field] = int(event[field])
            event["sleeper_stack"] = cls.fold_stack(event["sleeper_stack"])
            event["waker_stack"] = cls.fold_stack(event["waker_stack"])
            events.append(event)
        return events

    @classmethod
    def aggregate_matrix(cls, events: list[dict]) -> list[dict]:
        groups = defaultdict(list)
        for event in events:
            key = (
                event["sleeper_comm"],
                event["waker_comm"],
                event["sleeper_stack"],
                event["waker_stack"],
            )
            groups[key].append(event)
        rows = []
        for key, edge_events in groups.items():
            offcpu = [event["offcpu_ns"] for event in edge_events]
            rows.append(
                {
                    "sleeper_comm": key[0],
                    "waker_comm": key[1],
                    "sleeper_stack": key[2],
                    "waker_stack": key[3],
                    "count": len(edge_events),
                    "total_offcpu_ns": sum(offcpu),
                    "total_sleep_ns": sum(event["sleep_ns"] for event in edge_events),
                    "total_runq_ns": sum(event["runq_ns"] for event in edge_events),
                    "p50_offcpu_ns": cls.percentile(offcpu, 50),
                    "p95_offcpu_ns": cls.percentile(offcpu, 95),
                    "p99_offcpu_ns": cls.percentile(offcpu, 99),
                    "max_offcpu_ns": max(offcpu),
                }
            )
        return sorted(rows, key=lambda row: row["total_offcpu_ns"], reverse=True)

    @classmethod
    def program_for_target(cls, target: str) -> str:
        if not target or any(char in target for char in ('"', "\\", "\n")):
            raise ValueError("offcpu target comm must be a non-empty literal")
        return Path(resolve_path(cls.PROGRAM)).read_text().replace("__TARGET_COMM__", target)

    @staticmethod
    def fold_stack(stack: str) -> str:
        frames = [line.strip() for line in stack.splitlines() if line.strip()]
        return ";".join(reversed(frames)) if frames else "unknown"

    @staticmethod
    def percentile(values: list[int], percentile: int) -> int:
        if not values:
            return 0
        ordered = sorted(values)
        index = max(0, (len(ordered) * percentile + 99) // 100 - 1)
        return ordered[index]

    @classmethod
    def write_matrix(cls, rows: list[dict], path: str):
        with open(path, "w", newline="", encoding="utf-8") as output:
            writer = csv.DictWriter(output, fieldnames=cls.MATRIX_HEADER)
            writer.writeheader()
            writer.writerows(rows)

    @classmethod
    def parse_lost_events(cls, content: str) -> int:
        return sum(int(match) for match in cls.LOST_PATTERN.findall(content))

    def _read_errors(self) -> str:
        try:
            return Path(self.trace.err_file_name).read_text(encoding="utf-8")
        except OSError as error:
            bm_log(f"Could not read offcpu errors: {error}", LogType.ERROR)
            return ""

    @staticmethod
    def _application_name() -> str:
        if bm_config.g_config is None or len(bm_config.g_config.get_apps()) != 1:
            raise ValueError("offcpu requires exactly one configured application")
        return bm_config.g_config.get_apps()[0].name
