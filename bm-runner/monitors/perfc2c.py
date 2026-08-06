# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

import os
import re
import subprocess
from pathlib import Path

from monitors.monitor import Monitor
from monitors.perf import FlameGraph
from utils.logger import LogType, bm_log


class PerfC2C(Monitor):
    """Generate topology evidence and perf c2c summaries from Arm SPE samples."""

    REPORT_FILE = "perf-c2c.txt"
    ERROR_FILE = "perf-c2c.err"
    TOPOLOGY_FILE = "perf-c2c-topology.txt"
    METRICS = {
        "Total records": "records",
        "Load Operations": "loads",
        "Load L1D hit": "l1d_hits",
        "Load LLC hit": "llc_hits",
        "Load Local HITM": "local_hitm",
        "Load Remote HITM": "remote_hitm",
        "Load Local DRAM": "local_dram",
        "Load Remote DRAM": "remote_dram",
        "No Page Map Rejects": "page_map_rejects",
        "Total Shared Cache Lines": "shared_cachelines",
    }

    def __init__(self, output_dir: str, args: list[str] = []):
        super().__init__(dir=output_dir, args=args)
        self.name = "perf-c2c"

    def start(self):
        pass

    def stop(self):
        pass

    def collect_results(self) -> str:
        data_file = os.path.join(self.dir, FlameGraph.DATA_FILE)
        if not os.path.isfile(data_file):
            bm_log(f"{self.name} could not find {FlameGraph.DATA_FILE}", LogType.ERROR)
            return ""
        self._write_topology()
        command = ["sudo", "perf", "c2c", "report", "-i", data_file, "--stdio"]
        report = subprocess.run(command, text=True, capture_output=True, check=False)
        Path(self.dir, self.REPORT_FILE).write_text(report.stdout, encoding="utf-8")
        Path(self.dir, self.ERROR_FILE).write_text(report.stderr, encoding="utf-8")
        if report.returncode != 0:
            bm_log(f"{self.name} report failed with exit {report.returncode}", LogType.ERROR)
            return ""
        metrics = self.parse_metrics(report.stdout)
        return "".join(f"perf_c2c_{name}={metrics.get(name, 0)};" for name in self.METRICS.values())

    @classmethod
    def parse_metrics(cls, report: str) -> dict[str, int]:
        metrics = {}
        for label, name in cls.METRICS.items():
            match = re.search(rf"^\s*{re.escape(label)}\s*:\s*([0-9]+)\s*$", report, re.MULTILINE)
            if match:
                metrics[name] = int(match.group(1))
        return metrics

    @staticmethod
    def is_supported() -> bool:
        return FlameGraph.arm_spe_supported()

    @staticmethod
    def get_args() -> list[str]:
        if FlameGraph.arm_spe_enabled():
            return []
        return ["-e", FlameGraph.arm_spe_event()]

    def _write_topology(self):
        topology = subprocess.run(
            ["lscpu", "-e=CPU,NODE,SOCKET,CORE,CACHE"],
            text=True,
            capture_output=True,
            check=False,
        )
        Path(self.dir, self.TOPOLOGY_FILE).write_text(
            topology.stdout + topology.stderr, encoding="utf-8"
        )
        if topology.returncode != 0:
            bm_log(f"{self.name} topology snapshot failed", LogType.ERROR)
