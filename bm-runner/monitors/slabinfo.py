# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

import os
import re
from pathlib import Path

import matplotlib.pyplot as plt

from monitors.monitor import Monitor
from utils.logger import bm_log, LogType


class SlabinfoStats(Monitor):
    INTERESTING_PATTERNS = (
        "dentry",
        "inode",
        "sock",
        "skbuff",
        "kmalloc",
        "cgroup",
        "file",
    )

    def __init__(self, output_dir: str, args: list[str] = []):
        super().__init__(dir=output_dir, args=args)
        self.slabinfo_file = Path(args[0]) if args else Path("/proc/slabinfo")
        self.patterns = tuple(args[1:]) if len(args) > 1 else self.INTERESTING_PATTERNS
        self.start_sample: dict[str, int] = {}
        self.stop_sample: dict[str, int] = {}

    @staticmethod
    def sanitize(name: str) -> str:
        return re.sub(r"[^A-Za-z0-9]+", "_", name.lower()).strip("_")

    @classmethod
    def parse_slabinfo(cls, text: str) -> dict[str, dict[str, int]]:
        results = {}
        for line in text.splitlines():
            fields = line.split()
            if len(fields) < 3 or fields[0].startswith("#") or fields[0] == "slabinfo":
                continue
            try:
                results[fields[0]] = {
                    "active_objs": int(fields[1]),
                    "num_objs": int(fields[2]),
                }
            except ValueError:
                continue
        return results

    def filter_sample(self, sample: dict[str, dict[str, int]]) -> dict[str, int]:
        results = {"slabinfo_active_objs": 0, "slabinfo_num_objs": 0}
        for name, values in sample.items():
            active = values["active_objs"]
            num = values["num_objs"]
            results["slabinfo_active_objs"] += active
            results["slabinfo_num_objs"] += num
            if any(pattern in name for pattern in self.patterns):
                prefix = f"slabinfo_{self.sanitize(name)}"
                results[f"{prefix}_active_objs"] = active
                results[f"{prefix}_num_objs"] = num
        return results

    def read_sample(self) -> dict[str, int]:
        try:
            return self.filter_sample(self.parse_slabinfo(self.slabinfo_file.read_text()))
        except FileNotFoundError:
            bm_log(f"{self.slabinfo_file} is not available", LogType.WARNING)
            return {}

    @staticmethod
    def delta(start: dict[str, int], stop: dict[str, int]) -> dict[str, int]:
        return {f"{key}_delta": value - start.get(key, value) for key, value in stop.items()}

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
            "slabinfo_active_objs_delta",
            "slabinfo_num_objs_delta",
            "slabinfo_dentry_active_objs_delta",
            "slabinfo_inode_cache_active_objs_delta",
            "slabinfo_skbuff_head_cache_active_objs_delta",
        ]
        present = [key for key in keys if key in results]
        if not present:
            return
        plt.figure(dpi=150)
        plt.bar([key.removeprefix("slabinfo_").removesuffix("_delta") for key in present], [results[key] for key in present])
        plt.title("slabinfo object deltas")
        plt.ylabel("Objects")
        plt.xticks(rotation=30, ha="right")
        plt.tight_layout()
        plt.savefig(os.path.join(self.dir, "slabinfo-delta.png"))
        plt.close()
