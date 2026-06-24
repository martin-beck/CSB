# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

import os
import re
from typing import Optional

import matplotlib.pyplot as plt

from monitors.monitor import Monitor


class PidstatStats(Monitor):
    INTERVAL = 1
    DEFAULT_ARGS = ["-h", "-t", "-u", "-w", "-d", "-r"]

    def __init__(self, output_dir: str, args: list[str] = []):
        from utils.process import BackgroundProcess

        super().__init__(dir=output_dir, args=args)
        pidstat_args = args if args else self.DEFAULT_ARGS
        cmds = ["pidstat"]
        cmds.extend(pidstat_args)
        cmds.append(str(self.INTERVAL))
        self.pidstat = BackgroundProcess(
            name="pidstat",
            ofile_name="pidstat.log",
            cmds=cmds,
            out_dir=output_dir,
            requires=["pidstat"],
            pin=self.get_cpus(),
        )

    @staticmethod
    def sanitize(name: str) -> str:
        name = name.replace("%", "pct_").replace("/", "_per_")
        return re.sub(r"[^A-Za-z0-9]+", "_", name.lower()).strip("_")

    @classmethod
    def aggregate_output(cls, text: str) -> dict[str, float]:
        header: list[str] = []
        values: dict[str, list[float]] = {}
        skip_columns = {"uid", "pid", "tgid", "tid", "command"}
        for line in text.splitlines():
            fields = line.split()
            if not fields or fields[0].startswith("Linux"):
                continue
            if "UID" in fields and "Command" in fields:
                header = fields[fields.index("UID") :]
                continue
            if not header or len(fields) < len(header):
                continue
            row = fields[-len(header) :]
            for key, value in zip(header, row):
                metric = cls.sanitize(key)
                if metric in skip_columns:
                    continue
                try:
                    values.setdefault(metric, []).append(float(value))
                except ValueError:
                    continue
        return {
            f"pidstat_{key}_avg": sum(samples) / len(samples)
            for key, samples in values.items()
            if samples
        }

    def start(self):
        self.pidstat.start()

    def stop(self):
        self.pidstat.stop()

    def collect_results(self, pids: Optional[list[int]] = None) -> str:
        results = self.aggregate_output(self.pidstat.read_output())
        if results:
            self.dump_plot(results)
        return "".join(f"{key}={value};" for key, value in sorted(results.items()))

    def dump_plot(self, results: dict[str, float]):
        keys = [
            "pidstat_pct_usr_avg",
            "pidstat_pct_system_avg",
            "pidstat_cswch_per_s_avg",
            "pidstat_nvcswch_per_s_avg",
            "pidstat_kb_rd_per_s_avg",
            "pidstat_kb_wr_per_s_avg",
            "pidstat_minflt_per_s_avg",
            "pidstat_majflt_per_s_avg",
        ]
        present = [key for key in keys if key in results]
        if not present:
            return
        plt.figure(dpi=150)
        plt.bar([key.removeprefix("pidstat_").removesuffix("_avg") for key in present], [results[key] for key in present])
        plt.title("pidstat averaged task metrics")
        plt.xticks(rotation=30, ha="right")
        plt.tight_layout()
        plt.savefig(os.path.join(self.dir, "pidstat-avg.png"))
        plt.close()
