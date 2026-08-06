# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

import json

from config.benchmark import MonitorType
from monitors.monitor_factory import MonitorFactory
from monitors.psi_cgroup import PsiCgroup


def test_parse_pressure():
    assert PsiCgroup.parse_pressure(
        "some avg10=1.25 avg60=0.50 avg300=0.10 total=1234\n"
        "full avg10=0.25 avg60=0.20 avg300=0.05 total=234\n"
    ) == {
        "some": {"avg10": 1.25, "avg60": 0.5, "avg300": 0.1, "total": 1234},
        "full": {"avg10": 0.25, "avg60": 0.2, "avg300": 0.05, "total": 234},
    }


def test_collect_results_uses_total_delta(tmp_path):
    monitor = PsiCgroup(str(tmp_path))
    monitor._samples = [
        {
            "timestamp": 10.0,
            "pressure": {"host": {"cpu": {"some": {"total": 100}}}},
        },
        {
            "timestamp": 12.0,
            "pressure": {"host": {"cpu": {"some": {"total": 40100}}}},
        },
    ]

    assert monitor.collect_results() == (
        "psi_host_cpu_some_total_us=40000;psi_host_cpu_some_percent=2.0;"
    )


def test_samples_host_and_cgroup_pressure(monkeypatch, tmp_path):
    host = tmp_path / "host"
    cgroup = tmp_path / "cgroup"
    host.mkdir()
    cgroup.mkdir()
    for resource in PsiCgroup.RESOURCES:
        (host / resource).write_text("some avg10=0 avg60=0 avg300=0 total=1\n")
        (cgroup / f"{resource}.pressure").write_text("some avg10=0 avg60=0 avg300=0 total=2\n")
    monkeypatch.setattr(PsiCgroup, "HOST_PRESSURE_DIR", host)
    monitor = PsiCgroup(str(tmp_path), [str(cgroup)])

    monitor._sample()

    assert monitor._samples[0]["pressure"]["host"]["cpu"]["some"]["total"] == 1
    assert monitor._samples[0]["pressure"]["cgroup_0"]["io"]["some"]["total"] == 2


def test_stop_preserves_raw_samples(tmp_path):
    monitor = PsiCgroup(str(tmp_path))
    monitor._samples = [{"timestamp": 1.0, "pressure": {}}]

    monitor.stop()

    lines = (tmp_path / "psi-cgroup.jsonl").read_text().splitlines()
    assert json.loads(lines[0]) == {"pressure": {}, "timestamp": 1.0}


def test_factory_creates_psi_monitor(tmp_path):
    monitor = MonitorFactory.create(MonitorType.PSI_CGROUP, str(tmp_path), [])

    assert isinstance(monitor, PsiCgroup)
