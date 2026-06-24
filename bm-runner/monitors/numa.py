# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

import os
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt

from monitors.monitor import Monitor
from utils.logger import bm_log, LogType


class NumaStats(Monitor):
    def __init__(self, output_dir: str, args: list[str] = []):
        super().__init__(dir=output_dir, args=args)
        self.node_root = Path(args[0]) if args else Path("/sys/devices/system/node")
        self.start_sample: dict[str, int] = {}
        self.stop_sample: dict[str, int] = {}

    @staticmethod
    def parse_numastat(text: str) -> dict[str, int]:
        results = {}
        for line in text.splitlines():
            fields = line.split()
            if len(fields) == 2:
                results[fields[0]] = int(fields[1])
        return results

    def read_sample(self) -> dict[str, int]:
        totals: dict[str, int] = {}
        nodes = sorted(self.node_root.glob("node[0-9]*"))
        if not nodes:
            bm_log(f"No NUMA nodes found under {self.node_root}", LogType.WARNING)
        for node in nodes:
            path = node / "numastat"
            try:
                node_sample = self.parse_numastat(path.read_text())
            except FileNotFoundError:
                bm_log(f"{path} is not available", LogType.WARNING)
                continue
            node_name = node.name
            for key, value in node_sample.items():
                totals[f"numa_{key}"] = totals.get(f"numa_{key}", 0) + value
                totals[f"numa_{node_name}_{key}"] = value
        totals["numa_node_count"] = len(nodes)
        return totals

    @staticmethod
    def delta(start: dict[str, int], stop: dict[str, int]) -> dict[str, int]:
        results = {}
        for key, value in stop.items():
            if key == "numa_node_count":
                results[key] = value
            else:
                results[f"{key}_delta"] = value - start.get(key, value)
        return results

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
            "numa_numa_hit_delta",
            "numa_numa_miss_delta",
            "numa_numa_foreign_delta",
            "numa_interleave_hit_delta",
            "numa_local_node_delta",
            "numa_other_node_delta",
        ]
        values = [results.get(key, 0) for key in keys]
        plt.figure(dpi=150)
        plt.bar([key.removeprefix("numa_").removesuffix("_delta") for key in keys], values)
        plt.title("NUMA counter deltas")
        plt.ylabel("Pages")
        plt.xticks(rotation=30, ha="right")
        plt.tight_layout()
        plt.savefig(os.path.join(self.dir, "numa-delta.png"))
        plt.close()
