# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

import os
import re
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt

from monitors.monitor import Monitor
from utils.logger import bm_log, LogType


class IrqSoftirqStats(Monitor):
    def __init__(self, output_dir: str, args: list[str] = []):
        super().__init__(dir=output_dir, args=args)
        self.proc_dir = Path(args[0]) if args else Path("/proc")
        self.start_sample: dict[str, int] = {}
        self.stop_sample: dict[str, int] = {}

    @staticmethod
    def sanitize(name: str) -> str:
        return re.sub(r"[^A-Za-z0-9]+", "_", name.strip().lower()).strip("_")

    @classmethod
    def parse_interrupts(cls, text: str) -> dict[str, int]:
        results = {"irq_total": 0}
        for line in text.splitlines():
            if ":" not in line:
                continue
            label, rest = line.split(":", 1)
            fields = rest.split()
            counts = []
            for field in fields:
                if field.isdigit():
                    counts.append(int(field))
                else:
                    break
            if not counts:
                continue
            total = sum(counts)
            key = cls.sanitize(label)
            results[f"irq_{key}"] = results.get(f"irq_{key}", 0) + total
            results["irq_total"] += total
        return results

    @classmethod
    def parse_softirqs(cls, text: str) -> dict[str, int]:
        results = {"softirq_total": 0}
        for line in text.splitlines():
            if ":" not in line:
                continue
            label, rest = line.split(":", 1)
            counts = [int(field) for field in rest.split() if field.isdigit()]
            if not counts:
                continue
            total = sum(counts)
            key = cls.sanitize(label)
            results[f"softirq_{key}"] = total
            results["softirq_total"] += total
        return results

    @staticmethod
    def parse_stat(text: str) -> dict[str, int]:
        wanted = {"intr", "ctxt", "processes", "procs_running", "procs_blocked"}
        results = {}
        for line in text.splitlines():
            fields = line.split()
            if fields and fields[0] in wanted and len(fields) > 1:
                results[f"proc_stat_{fields[0]}"] = int(fields[1])
        return results

    def read_sample(self) -> dict[str, int]:
        sample = {}
        readers = {
            "interrupts": self.parse_interrupts,
            "softirqs": self.parse_softirqs,
            "stat": self.parse_stat,
        }
        for name, parser in readers.items():
            path = self.proc_dir / name
            try:
                sample.update(parser(path.read_text()))
            except FileNotFoundError:
                bm_log(f"{path} is not available", LogType.WARNING)
        return sample

    @staticmethod
    def delta(start: dict[str, int], stop: dict[str, int]) -> dict[str, int]:
        return {f"{key}_delta": value - start.get(key, value) for key, value in stop.items()}

    def start(self):
        self.start_sample = self.read_sample()

    def stop(self):
        self.stop_sample = self.read_sample()

    def collect_results(self, pids: Optional[list[int]] = None) -> str:
        results = self.delta(self.start_sample, self.stop_sample)
        if results:
            self.dump_plot(results)
        return "".join(f"{key}={value};" for key, value in sorted(results.items()))

    def dump_plot(self, results: dict[str, int]):
        keys = ["irq_total_delta", "softirq_total_delta", "proc_stat_intr_delta"]
        values = [results.get(key, 0) for key in keys]
        plt.figure(dpi=150)
        plt.bar([key.removesuffix("_delta") for key in keys], values)
        plt.title("Interrupt and softirq deltas")
        plt.ylabel("Events")
        plt.xticks(rotation=25, ha="right")
        plt.tight_layout()
        plt.savefig(os.path.join(self.dir, "irq-softirq-delta.png"))
        plt.close()
