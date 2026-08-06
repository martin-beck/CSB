# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

import json
import time
from pathlib import Path

from monitors.monitor import Monitor
from utils.logger import LogType, bm_log


class NumaLocality(Monitor):
    """Capture host and per-node NUMA allocation and migration deltas."""

    VMSTAT = Path("/proc/vmstat")
    NODE_GLOB = "/sys/devices/system/node/node*/vmstat"
    OUTPUT_FILE = "numa-locality.json"
    COUNTERS = {
        "numa_hit",
        "numa_miss",
        "numa_foreign",
        "numa_interleave",
        "numa_local",
        "numa_other",
        "numa_hint_faults",
        "numa_hint_faults_local",
        "numa_pages_migrated",
        "pgmigrate_success",
        "pgmigrate_fail",
    }

    def __init__(self, output_dir: str, args: list[str] = []):
        super().__init__(dir=output_dir, args=args)
        self.name = "numa-locality"
        self._samples: list[dict] = []

    def start(self):
        self._samples.append(self.sample())

    def stop(self):
        self._samples.append(self.sample())
        Path(self.dir, self.OUTPUT_FILE).write_text(
            json.dumps(self._samples, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def collect_results(self) -> str:
        if len(self._samples) < 2:
            return ""
        first, last = self._samples[0], self._samples[-1]
        global_delta = self.delta(first["global"], last["global"])
        output = "".join(f"{key}_delta={value};" for key, value in sorted(global_delta.items()))
        output += f"numa_local_percent={self.ratio(global_delta, 'numa_local', 'numa_other')};"
        output += (
            "numa_hint_local_percent="
            f"{self.ratio(global_delta, 'numa_hint_faults_local', 'numa_hint_faults')};"
        )
        for node, values in sorted(last["nodes"].items()):
            node_delta = self.delta(first["nodes"].get(node, {}), values)
            output += f"numa_{node}_local_delta={node_delta.get('numa_local', 0)};"
            output += f"numa_{node}_other_delta={node_delta.get('numa_other', 0)};"
        return output

    def sample(self) -> dict:
        nodes = {}
        for path in sorted(Path("/").glob(self.NODE_GLOB.removeprefix("/"))):
            nodes[path.parent.name] = self.read_counters(path)
        return {
            "timestamp": time.monotonic(),
            "global": self.read_counters(self.VMSTAT),
            "nodes": nodes,
        }

    @classmethod
    def read_counters(cls, path: Path) -> dict[str, int]:
        try:
            fields = (line.split() for line in path.read_text(encoding="utf-8").splitlines())
            return {name: int(value) for name, value in fields if name in cls.COUNTERS}
        except (FileNotFoundError, PermissionError, OSError, ValueError) as error:
            bm_log(f"Could not read NUMA counters from {path}: {error}", LogType.ERROR)
            return {}

    @staticmethod
    def delta(first: dict[str, int], last: dict[str, int]) -> dict[str, int]:
        return {key: max(0, value - first.get(key, value)) for key, value in last.items()}

    @staticmethod
    def ratio(values: dict[str, int], numerator: str, denominator: str) -> float:
        total = values.get(denominator, 0)
        if numerator == "numa_local":
            total += values.get(numerator, 0)
        if total == 0:
            return 0.0
        return 100.0 * values.get(numerator, 0) / total
