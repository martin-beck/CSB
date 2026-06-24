# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

import os
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt

from monitors.monitor import Monitor
from utils.logger import bm_log, LogType


class PressureStallStats(Monitor):
    DEFAULT_FILES = ("cpu", "memory", "io")

    def __init__(self, output_dir: str, args: list[str] = []):
        super().__init__(dir=output_dir, args=args)
        self.pressure_dir = Path(args[0]) if args else Path("/proc/pressure")
        self.files = args[1:] if len(args) > 1 else list(self.DEFAULT_FILES)
        self.start_sample: dict[str, dict[str, dict[str, float]]] = {}
        self.stop_sample: dict[str, dict[str, dict[str, float]]] = {}

    @staticmethod
    def parse_pressure(text: str) -> dict[str, dict[str, float]]:
        sample: dict[str, dict[str, float]] = {}
        for line in text.splitlines():
            fields = line.split()
            if not fields:
                continue
            level = fields[0]
            sample[level] = {}
            for field in fields[1:]:
                key, value = field.split("=", 1)
                sample[level][key] = float(value)
        return sample

    def read_sample(self) -> dict[str, dict[str, dict[str, float]]]:
        sample = {}
        for name in self.files:
            path = self.pressure_dir / name
            try:
                sample[name] = self.parse_pressure(path.read_text())
            except FileNotFoundError:
                bm_log(f"PSI file {path} is not available", LogType.WARNING)
        return sample

    @staticmethod
    def flatten_delta(
        start: dict[str, dict[str, dict[str, float]]],
        stop: dict[str, dict[str, dict[str, float]]],
    ) -> dict[str, float]:
        results = {}
        for resource, levels in stop.items():
            for level, metrics in levels.items():
                for metric, value in metrics.items():
                    key = f"psi_{resource}_{level}_{metric}"
                    if metric == "total":
                        start_value = start.get(resource, {}).get(level, {}).get(metric, value)
                        results[f"{key}_delta"] = value - start_value
                    else:
                        results[key] = value
        return results

    def start(self):
        self.start_sample = self.read_sample()

    def stop(self):
        self.stop_sample = self.read_sample()

    def collect_results(self, pids: Optional[list[int]] = None) -> str:
        results = self.flatten_delta(self.start_sample, self.stop_sample)
        if results:
            self.dump_plot(results)
        return "".join(f"{key}={value};" for key, value in sorted(results.items()))

    def dump_plot(self, results: dict[str, float]):
        delta_items = {k: v for k, v in results.items() if k.endswith("_total_delta")}
        if not delta_items:
            return
        labels = [key.removeprefix("psi_").removesuffix("_total_delta") for key in delta_items]
        values = list(delta_items.values())
        plt.figure(dpi=150)
        plt.bar(labels, values)
        plt.title("PSI total stall delta")
        plt.ylabel("Microseconds")
        plt.xticks(rotation=30, ha="right")
        plt.tight_layout()
        plt.savefig(os.path.join(self.dir, "psi-total-delta.png"))
        plt.close()
