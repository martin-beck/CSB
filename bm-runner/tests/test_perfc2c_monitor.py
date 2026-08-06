# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

from types import SimpleNamespace
from unittest.mock import patch

from config.benchmark import BenchmarkConfig, MonitorType
from monitors.perfc2c import PerfC2C


REPORT = """
  Total records                     :      75491
  Load Operations                   :      58084
  Load L1D hit                      :      52946
  Load LLC hit                      :       1886
  Load Local HITM                   :          2
  Load Remote HITM                  :          3
  No Page Map Rejects               :        610
  Total Shared Cache Lines          :          5
"""


def test_parse_c2c_metrics():
    metrics = PerfC2C.parse_metrics(REPORT)

    assert metrics["records"] == 75491
    assert metrics["remote_hitm"] == 3
    assert metrics["shared_cachelines"] == 5


def test_collect_preserves_report_and_topology(monkeypatch, tmp_path):
    (tmp_path / "perf.data").touch()
    monitor = PerfC2C(str(tmp_path))
    monkeypatch.setattr(monitor, "_write_topology", lambda: None)
    completed = SimpleNamespace(stdout=REPORT, stderr="warning", returncode=0)

    with patch("monitors.perfc2c.subprocess.run", return_value=completed):
        result = monitor.collect_results()

    assert "perf_c2c_records=75491;" in result
    assert "perf_c2c_remote_hitm=3;" in result
    assert (tmp_path / PerfC2C.REPORT_FILE).read_text() == REPORT
    assert (tmp_path / PerfC2C.ERROR_FILE).read_text() == "warning"


def test_collect_rejects_failed_report(monkeypatch, tmp_path):
    (tmp_path / "perf.data").touch()
    monitor = PerfC2C(str(tmp_path))
    monkeypatch.setattr(monitor, "_write_topology", lambda: None)
    completed = SimpleNamespace(stdout="", stderr="failed", returncode=1)

    with patch("monitors.perfc2c.subprocess.run", return_value=completed):
        assert monitor.collect_results() == ""


def test_config_adds_perf_and_spe_event(monkeypatch):
    monkeypatch.setenv("CSB_ANALYZE", "true")
    monkeypatch.setattr(PerfC2C, "is_supported", lambda: True)
    monkeypatch.setattr(PerfC2C, "get_args", lambda: ["-e", "arm_spe_0/test/"])

    config = BenchmarkConfig(monitors={MonitorType.PERF_C2C: []})

    assert list(config.monitors) == [MonitorType.PERF, MonitorType.PERF_C2C]
    assert config.monitors[MonitorType.PERF] == ["-e", "arm_spe_0/test/"]


def test_config_removes_c2c_without_spe(monkeypatch):
    monkeypatch.setenv("CSB_ANALYZE", "true")
    monkeypatch.setattr(PerfC2C, "is_supported", lambda: False)

    config = BenchmarkConfig(monitors={MonitorType.PERF_C2C: []})

    assert MonitorType.PERF_C2C not in config.monitors
    assert MonitorType.PERF not in config.monitors
