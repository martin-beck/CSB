# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

import csv
import os
import re
import subprocess
from collections import defaultdict
from pathlib import Path

from bm_utils import is_perf_event_supported
from monitors.monitor import Monitor
from monitors.perf import FlameGraph
from utils.logger import LogType, bm_log


class IpiTlb(Monitor):
    """Postprocess IPI source/target and TLB shootdown amplification."""

    EVENTS = [
        "tlb:tlb_flush",
        "ipi:ipi_entry",
        "ipi:ipi_exit",
        "ipi:ipi_raise",
        "ipi:ipi_send_cpu",
        "ipi:ipi_send_cpumask",
    ]
    RAW_FILE = "ipi-tlb-events.txt"
    ERROR_FILE = "ipi-tlb.err"
    SEND_MATRIX = "ipi-send-matrix.csv"
    HANDLER_MATRIX = "ipi-handler-matrix.csv"
    TLB_MATRIX = "tlb-flush-matrix.csv"
    LINE_PATTERN = re.compile(
        r"^\[(?P<cpu>\d+)\]\s+(?P<time>[0-9.]+):\s+"
        r"(?P<event>(?:ipi|tlb):[^:]+):\s+(?P<payload>.*)$",
        re.MULTILINE,
    )
    SEND_PATTERN = re.compile(r"cpu=(\d+) callsite=(\S+) callback=(\S+)")
    TLB_PATTERN = re.compile(r"pages:(\d+) reason:(.*) \((\d+)\)$")

    def __init__(self, output_dir: str, args: list[str] = []):
        super().__init__(dir=output_dir, args=args)
        self.name = "ipi-tlb"

    def start(self):
        pass

    def stop(self):
        pass

    def collect_results(self) -> str:
        data_file = os.path.join(self.dir, FlameGraph.DATA_FILE)
        if not os.path.isfile(data_file):
            bm_log(f"{self.name} could not find {FlameGraph.DATA_FILE}", LogType.ERROR)
            return ""
        command = [
            "sudo",
            "perf",
            "script",
            "-i",
            data_file,
            "-F",
            "trace:cpu,time,event,trace",
        ]
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        Path(self.dir, self.RAW_FILE).write_text(completed.stdout, encoding="utf-8")
        Path(self.dir, self.ERROR_FILE).write_text(completed.stderr, encoding="utf-8")
        if completed.returncode != 0:
            bm_log(
                f"{self.name} perf script failed with exit {completed.returncode}", LogType.ERROR
            )
            return ""
        sends, handlers, flushes = self.parse_events(completed.stdout)
        send_rows = self.aggregate_sends(sends)
        handler_rows = self.aggregate_handlers(handlers)
        tlb_rows = self.aggregate_tlb(flushes)
        self.write_rows(send_rows, Path(self.dir, self.SEND_MATRIX))
        self.write_rows(handler_rows, Path(self.dir, self.HANDLER_MATRIX))
        self.write_rows(tlb_rows, Path(self.dir, self.TLB_MATRIX))
        durations = [event["duration_ns"] for event in handlers]
        return (
            f"ipi_sends={len(sends)};"
            f"ipi_unique_targets={len({event['target_cpu'] for event in sends})};"
            f"ipi_handler_events={len(handlers)};"
            f"ipi_handler_total_ns={sum(durations)};"
            f"ipi_handler_p95_ns={self.percentile(durations, 95)};"
            f"tlb_flushes={len(flushes)};"
            f"tlb_pages={sum(event['pages'] for event in flushes)};"
            f"tlb_remote_shootdowns={sum(event['reason_id'] == 1 for event in flushes)};"
        )

    @classmethod
    def parse_events(cls, content: str) -> tuple[list[dict], list[dict], list[dict]]:
        sends, handlers, flushes = [], [], []
        active_handlers = {}
        for match in cls.LINE_PATTERN.finditer(content):
            cpu = int(match["cpu"])
            timestamp_ns = int(float(match["time"]) * 1_000_000_000)
            event, payload = match["event"], match["payload"]
            if event == "ipi:ipi_send_cpu" and (send := cls.SEND_PATTERN.search(payload)):
                sends.append(
                    {
                        "source_cpu": cpu,
                        "target_cpu": int(send.group(1)),
                        "callsite": send.group(2),
                        "callback": send.group(3),
                    }
                )
            elif event == "ipi:ipi_entry":
                active_handlers[(cpu, payload)] = timestamp_ns
            elif event == "ipi:ipi_exit":
                start = active_handlers.pop((cpu, payload), None)
                if start is not None:
                    handlers.append(
                        {
                            "cpu": cpu,
                            "reason": payload.strip("()"),
                            "duration_ns": timestamp_ns - start,
                        }
                    )
            elif event == "tlb:tlb_flush" and (flush := cls.TLB_PATTERN.search(payload)):
                flushes.append(
                    {
                        "cpu": cpu,
                        "pages": int(flush.group(1)),
                        "reason": flush.group(2),
                        "reason_id": int(flush.group(3)),
                    }
                )
        return sends, handlers, flushes

    @classmethod
    def aggregate_sends(cls, events: list[dict]) -> list[dict]:
        counts = defaultdict(int)
        for event in events:
            counts[
                (event["source_cpu"], event["target_cpu"], event["callsite"], event["callback"])
            ] += 1
        return [
            {
                "source_cpu": key[0],
                "target_cpu": key[1],
                "callsite": key[2],
                "callback": key[3],
                "count": count,
            }
            for key, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)
        ]

    @classmethod
    def aggregate_handlers(cls, events: list[dict]) -> list[dict]:
        groups = defaultdict(list)
        for event in events:
            groups[(event["cpu"], event["reason"])].append(event["duration_ns"])
        return [
            {
                "cpu": key[0],
                "reason": key[1],
                "count": len(values),
                "total_ns": sum(values),
                "p95_ns": cls.percentile(values, 95),
                "max_ns": max(values),
            }
            for key, values in sorted(groups.items(), key=lambda item: sum(item[1]), reverse=True)
        ]

    @staticmethod
    def aggregate_tlb(events: list[dict]) -> list[dict]:
        groups = defaultdict(lambda: {"count": 0, "pages": 0})
        for event in events:
            values = groups[(event["cpu"], event["reason_id"], event["reason"])]
            values["count"] += 1
            values["pages"] += event["pages"]
        return [
            {"cpu": key[0], "reason_id": key[1], "reason": key[2], **values}
            for key, values in sorted(
                groups.items(), key=lambda item: item[1]["pages"], reverse=True
            )
        ]

    @staticmethod
    def percentile(values: list[int], percentile: int) -> int:
        if not values:
            return 0
        ordered = sorted(values)
        return ordered[max(0, (len(ordered) * percentile + 99) // 100 - 1)]

    @staticmethod
    def write_rows(rows: list[dict], path: Path):
        headers = list(rows[0]) if rows else []
        with path.open("w", newline="", encoding="utf-8") as output:
            if headers:
                writer = csv.DictWriter(output, fieldnames=headers)
                writer.writeheader()
                writer.writerows(rows)

    @classmethod
    def is_supported(cls) -> bool:
        return all(is_perf_event_supported(event) for event in cls.EVENTS)

    @classmethod
    def get_args(cls) -> list[str]:
        return [argument for event in cls.EVENTS for argument in ("-e", event)]
