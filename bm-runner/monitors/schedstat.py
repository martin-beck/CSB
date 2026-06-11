# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

import os
from pathlib import Path

import matplotlib.pyplot as plt

from monitors.monitor import Monitor
from utils.logger import bm_log, LogType


class SchedstatStats(Monitor):
    FIELD_NAMES = {
        7: "cpu_time_ns",
        8: "run_delay_ns",
        9: "timeslices",
    }

    def __init__(self, output_dir: str, args: list[str] = []):
        super().__init__(dir=output_dir, args=args)
        self.schedstat_file = Path(args[0]) if args else Path("/proc/schedstat")
        self.start_sample: dict[str, int] = {}
        self.stop_sample: dict[str, int] = {}

    @classmethod
    def parse_schedstat(cls, text: str) -> dict[str, int]:
        totals = {f"schedstat_{name}": 0 for name in cls.FIELD_NAMES.values()}
        cpu_count = 0
        for line in text.splitlines():
            fields = line.split()
            if not fields or not fields[0].startswith("cpu") or not fields[0][3:].isdigit():
                continue
            cpu_count += 1
            for index, name in cls.FIELD_NAMES.items():
                if len(fields) > index:
                    totals[f"schedstat_{name}"] += int(fields[index])
        totals["schedstat_cpu_count"] = cpu_count
        return totals

    def read_sample(self) -> dict[str, int]:
        try:
            return self.parse_schedstat(self.schedstat_file.read_text())
        except FileNotFoundError:
            bm_log(f"{self.schedstat_file} is not available", LogType.WARNING)
            return {}

    @staticmethod
    def delta(start: dict[str, int], stop: dict[str, int]) -> dict[str, int]:
        results = {}
        for key, value in stop.items():
            if key == "schedstat_cpu_count":
                results[key] = value
            else:
                results[f"{key}_delta"] = value - start.get(key, value)
        return results

    def start(self):
        self.start_sample = self.read_sample()

    def stop(self):
        self.stop_sample = self.read_sample()

    def collect_results(self) -> str:
        results = self.delta(self.start_sample, self.stop_sample)
        if results:
            self.dump_plot(results)
        return "".join(f"{key}={value};" for key, value in sorted(results.items()))

    def dump_plot(self, results: dict[str, int]):
        keys = [
            "schedstat_cpu_time_ns_delta",
            "schedstat_run_delay_ns_delta",
            "schedstat_timeslices_delta",
        ]
        values = [results.get(key, 0) for key in keys]
        plt.figure(dpi=150)
        plt.bar([key.removeprefix("schedstat_").removesuffix("_delta") for key in keys], values)
        plt.title("Scheduler counter deltas")
        plt.xticks(rotation=25, ha="right")
        plt.tight_layout()
        plt.savefig(os.path.join(self.dir, "schedstat-delta.png"))
        plt.close()
