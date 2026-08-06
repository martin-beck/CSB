# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

import os
import pandas as pd
from monitors.monitor import Monitor
from utils.logger import bm_log, LogType
from benchkit.shell.shell import shell_out
from bm_utils import read_data_frame_from_csv
from visual.plotchart import PlotConfig, PlotChart
from bm_utils import is_perf_event_supported
from monitors.perf import FlameGraph


class PerfLock(Monitor):
    LOCK_CONTENTION_CSV = "lock-contention.csv"
    LOCK_IDENTITY_CSV = "lock-contention-identity.csv"
    TARGET_METRIC = "avg_wait"
    LOCK_CONTENTION_SEPARATOR = ";"
    LOCK_CONTENTION_TOP_N = 20

    REQUIRED_EVENTS = ["lock:contention_begin", "lock:contention_end"]

    # The command `perf lock contention -x ";"` will output a CSV with the following header
    # output: contended; total wait; max wait; avg wait; type; caller
    header = ["contended", "total_wait", "max_wait", "avg_wait", "type", "caller"]
    identity_header = [
        "contended",
        "total_wait",
        "max_wait",
        "avg_wait",
        "address",
        "symbol",
        "type",
    ]

    def __init__(self, output_dir: str, args: list[str] = ["-a"]):
        super().__init__(dir=output_dir, args=args)
        self.name = "perf-lock"
        self.perf_contention_csv = os.path.join(self.dir, self.LOCK_CONTENTION_CSV)
        self.perf_identity_csv = os.path.join(self.dir, self.LOCK_IDENTITY_CSV)

    def start(self):
        pass

    def stop(self):
        pass

    def collect_results(self):
        output = ""
        if self.__run_lock_contention(self.perf_contention_csv):
            df = read_data_frame_from_csv(self.perf_contention_csv, names=self.header)
            if df is not None and not df.empty:
                # dump detailed plot of head results
                self.__plot(df.head(self.LOCK_CONTENTION_TOP_N))
                # summary of all locks per run
                avg_wait = df["avg_wait"].mean()
                max_wait = df["max_wait"].max()
                total_wait = df["total_wait"].sum()
                # this will be appended to the final csv
                output += f"perf_lock_avg_wait={avg_wait};"
                output += f"perf_lock_max_wait={max_wait};"
                output += f"perf_lock_total_wait={total_wait};"
            else:
                bm_log(f"{self.name} did not produce a valid data-frame", LogType.ERROR)
        if self.__run_lock_contention(self.perf_identity_csv, lock_identity=True):
            identities = read_data_frame_from_csv(
                self.perf_identity_csv, names=self.identity_header
            )
            if identities is not None and not identities.empty:
                for column in ("address", "symbol", "type"):
                    identities[column] = identities[column].astype(str).str.strip()
                identities = identities.sort_values("total_wait", ascending=False)
                hottest = identities.iloc[0]
                self.__plot_identities(identities.head(self.LOCK_CONTENTION_TOP_N))
                output += f"perf_lock_unique_locks={len(identities)};"
                output += f"perf_lock_hottest_address={hottest['address']};"
                output += f"perf_lock_hottest_symbol={hottest['symbol']};"
                output += f"perf_lock_hottest_total_wait={hottest['total_wait']};"
            else:
                bm_log(f"{self.name} did not produce lock identities", LogType.ERROR)
        return output

    @staticmethod
    def is_supported() -> bool:
        for e in PerfLock.REQUIRED_EVENTS:
            if not is_perf_event_supported(e):
                return False
        return True

    @staticmethod
    def get_args() -> list[str]:
        args = []
        for event in PerfLock.REQUIRED_EVENTS:
            args.extend(["-e", event])
        return args

    def __run_lock_contention(self, output_file: str, lock_identity: bool = False) -> bool:
        cmd = [
            "sudo",
            "perf",
            "lock",
            "contention",
            "-k",  # sort by average wait
            self.TARGET_METRIC,
            "-i",  # input file is the output of `perf lock record`
            FlameGraph.DATA_FILE,
            "-x",  # output report should be a CSV with `;` as delimiter
            ";",
            "--output",
            output_file,
        ]
        if lock_identity:
            cmd.append("--lock-addr")
        if not os.path.exists(os.path.join(self.dir, FlameGraph.DATA_FILE)):
            bm_log(
                f"{self.name} Could not find {FlameGraph.DATA_FILE} in {self.dir}!", LogType.ERROR
            )
            return False
        try:
            # perf lock contention is not available on older kernel versions
            # the command can fail
            shell_out(command=cmd, current_dir=self.dir)
            return True
        except Exception:
            bm_log("perf lock raised an error, check if it is supported.", LogType.ERROR)
            return False

    def __plot(self, df: pd.DataFrame):
        subjects = [
            ("contended", "Contended"),
            ("avg_wait", "Average Wait"),
            ("total_wait", "Total Wait"),
            ("max_wait", "Max Wait"),
        ]
        for y, label in subjects:
            cfg = PlotConfig(
                y=y,
                y_lbl=label,
                x="caller",
                x_lbl="Caller Function",
                hue="type",
                hue_lbl="Lock Type",
                shape="barplot",
            )
            plot_file = os.path.join(self.dir, f"perf_lock_{y}")
            PlotChart.plot(cfg, df, plot_file)

    def __plot_identities(self, df: pd.DataFrame):
        for y, label in (("contended", "Contended"), ("total_wait", "Total Wait")):
            cfg = PlotConfig(
                y=y,
                y_lbl=label,
                x="symbol",
                x_lbl="Lock Identity",
                hue="type",
                hue_lbl="Lock Type",
                shape="barplot",
            )
            plot_file = os.path.join(self.dir, f"perf_lock_identity_{y}")
            PlotChart.plot(cfg, df, plot_file)
