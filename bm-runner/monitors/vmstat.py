# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

import os
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt

from monitors.monitor import Monitor
from utils.logger import bm_log, LogType


class VmstatStats(Monitor):
    DEFAULT_PREFIXES = (
        "pgfault",
        "pgmajfault",
        "pgscan_",
        "pgsteal_",
        "allocstall",
        "compact_",
        "numa_",
        "nr_dirty",
        "nr_writeback",
    )

    def __init__(self, output_dir: str, args: list[str] = []):
        super().__init__(dir=output_dir, args=args)
        self.vmstat_file = Path(args[0]) if args else Path("/proc/vmstat")
        self.prefixes = tuple(args[1:]) if len(args) > 1 else self.DEFAULT_PREFIXES
        self.start_sample: dict[str, int] = {}
        self.stop_sample: dict[str, int] = {}

    @staticmethod
    def parse_vmstat(text: str) -> dict[str, int]:
        results = {}
        for line in text.splitlines():
            fields = line.split()
            if len(fields) == 2:
                results[fields[0]] = int(fields[1])
        return results

    def filter_sample(self, sample: dict[str, int]) -> dict[str, int]:
        return {
            f"vmstat_{key}": value
            for key, value in sample.items()
            if any(key.startswith(prefix) for prefix in self.prefixes)
        }

    def read_sample(self) -> dict[str, int]:
        try:
            return self.filter_sample(self.parse_vmstat(self.vmstat_file.read_text()))
        except FileNotFoundError:
            bm_log(f"{self.vmstat_file} is not available", LogType.WARNING)
            return {}

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
        keys = [
            "vmstat_pgfault_delta",
            "vmstat_pgmajfault_delta",
            "vmstat_allocstall_delta",
            "vmstat_nr_dirty_delta",
            "vmstat_nr_writeback_delta",
        ]
        values = [results.get(key, 0) for key in keys]
        plt.figure(dpi=150)
        plt.bar([key.removeprefix("vmstat_").removesuffix("_delta") for key in keys], values)
        plt.title("vmstat selected deltas")
        plt.ylabel("Events/pages")
        plt.xticks(rotation=30, ha="right")
        plt.tight_layout()
        plt.savefig(os.path.join(self.dir, "vmstat-delta.png"))
        plt.close()
