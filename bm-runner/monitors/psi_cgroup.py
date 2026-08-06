# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

import json
import os
import re
import threading
import time
from pathlib import Path

from monitors.monitor import Monitor
from utils.logger import LogType, bm_log


class PsiCgroup(Monitor):
    """Sample host PSI and optional cgroup-v2 pressure files."""

    INTERVAL_SECONDS = 0.25
    HOST_PRESSURE_DIR = Path("/proc/pressure")
    RESOURCES = ("cpu", "memory", "io")

    def __init__(self, output_dir: str, args: list[str] = []):
        super().__init__(dir=output_dir, args=args)
        self.name = "psi-cgroup"
        self.output_file_name = os.path.join(output_dir, f"{self.name}.jsonl")
        self._sources = {"host": self.HOST_PRESSURE_DIR}
        self._sources.update({f"cgroup_{idx}": Path(path) for idx, path in enumerate(args)})
        self._samples: list[dict] = []
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self):
        self._sample()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join()
        self._sample()
        with open(self.output_file_name, "w", encoding="utf-8") as output:
            for sample in self._samples:
                output.write(json.dumps(sample, sort_keys=True) + "\n")

    def collect_results(self) -> str:
        if len(self._samples) < 2:
            return ""
        elapsed = self._samples[-1]["timestamp"] - self._samples[0]["timestamp"]
        if elapsed <= 0:
            return ""
        first = self._samples[0]["pressure"]
        last = self._samples[-1]["pressure"]
        output = ""
        for source, resources in last.items():
            for resource, scopes in resources.items():
                for scope, values in scopes.items():
                    previous = first.get(source, {}).get(resource, {}).get(scope)
                    if previous is None:
                        continue
                    total_delta = max(0, values["total"] - previous["total"])
                    key = self._sanitize(f"psi_{source}_{resource}_{scope}")
                    output += f"{key}_total_us={total_delta};"
                    output += f"{key}_percent={total_delta / (elapsed * 10000)};"
        return output

    def _run(self):
        while not self._stop_event.wait(self.INTERVAL_SECONDS):
            self._sample()

    def _sample(self):
        pressure = {}
        for source, directory in self._sources.items():
            resources = {}
            for resource in self.RESOURCES:
                path = (
                    directory / resource if source == "host" else directory / f"{resource}.pressure"
                )
                try:
                    resources[resource] = self.parse_pressure(path.read_text(encoding="utf-8"))
                except (FileNotFoundError, PermissionError, OSError) as error:
                    bm_log(f"Could not read PSI file {path}: {error}", LogType.ERROR)
            if resources:
                pressure[source] = resources
        self._samples.append({"timestamp": time.monotonic(), "pressure": pressure})

    @staticmethod
    def parse_pressure(content: str) -> dict[str, dict[str, float | int]]:
        parsed = {}
        for line in content.splitlines():
            fields = line.split()
            if not fields:
                continue
            values = {}
            for field in fields[1:]:
                key, value = field.split("=", 1)
                values[key] = int(value) if key == "total" else float(value)
            parsed[fields[0]] = values
        return parsed

    @staticmethod
    def _sanitize(value: str) -> str:
        return re.sub(r"[^0-9A-Za-z]+", "_", value).strip("_")
