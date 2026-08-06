# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

from types import SimpleNamespace
from unittest.mock import patch

from config.benchmark import BenchmarkConfig, MonitorType
from monitors.ipi_tlb import IpiTlb


RAW = """[294] 1.000001: ipi:ipi_send_cpu: cpu=3 callsite=check_preempt_curr+0x54 callback=0x0
[3] 1.000010: ipi:ipi_entry: (Rescheduling interrupts)
[3] 1.000014: ipi:ipi_exit: (Rescheduling interrupts)
[294] 1.000020: tlb:tlb_flush: pages:64 reason:remote shootdown (1)
"""


def test_parse_ipi_and_tlb_events():
    sends, handlers, flushes = IpiTlb.parse_events(RAW)

    assert sends == [
        {
            "source_cpu": 294,
            "target_cpu": 3,
            "callsite": "check_preempt_curr+0x54",
            "callback": "0x0",
        }
    ]
    assert handlers == [{"cpu": 3, "reason": "Rescheduling interrupts", "duration_ns": 4000}]
    assert flushes == [{"cpu": 294, "pages": 64, "reason": "remote shootdown", "reason_id": 1}]


def test_aggregate_matrices():
    sends, handlers, flushes = IpiTlb.parse_events(RAW + RAW)

    assert IpiTlb.aggregate_sends(sends)[0]["count"] == 2
    assert IpiTlb.aggregate_handlers(handlers)[0]["total_ns"] == 8000
    assert IpiTlb.aggregate_tlb(flushes)[0]["pages"] == 128


def test_collect_preserves_raw_and_summaries(tmp_path):
    (tmp_path / "perf.data").touch()
    monitor = IpiTlb(str(tmp_path))
    completed = SimpleNamespace(stdout=RAW, stderr="", returncode=0)

    with patch("monitors.ipi_tlb.subprocess.run", return_value=completed):
        result = monitor.collect_results()

    assert result == (
        "ipi_sends=1;ipi_unique_targets=1;ipi_handler_events=1;"
        "ipi_handler_total_ns=4000;ipi_handler_p95_ns=4000;"
        "tlb_flushes=1;tlb_pages=64;tlb_remote_shootdowns=1;"
    )
    assert (tmp_path / monitor.RAW_FILE).read_text() == RAW
    assert (tmp_path / monitor.SEND_MATRIX).is_file()


def test_collect_rejects_failed_perf_script(tmp_path):
    (tmp_path / "perf.data").touch()
    monitor = IpiTlb(str(tmp_path))
    completed = SimpleNamespace(stdout="", stderr="failed", returncode=1)

    with patch("monitors.ipi_tlb.subprocess.run", return_value=completed):
        assert monitor.collect_results() == ""


def test_config_adds_perf_tracepoints(monkeypatch):
    monkeypatch.setenv("CSB_ANALYZE", "true")
    monkeypatch.setattr(IpiTlb, "is_supported", lambda: True)
    monkeypatch.setattr(IpiTlb, "get_args", lambda: ["-e", "tlb:tlb_flush"])

    config = BenchmarkConfig(monitors={MonitorType.IPI_TLB: []})

    assert list(config.monitors) == [MonitorType.PERF, MonitorType.IPI_TLB]
    assert config.monitors[MonitorType.PERF] == ["-e", "tlb:tlb_flush"]


def test_config_removes_monitor_when_tracepoints_missing(monkeypatch):
    monkeypatch.setenv("CSB_ANALYZE", "true")
    monkeypatch.setattr(IpiTlb, "is_supported", lambda: False)

    config = BenchmarkConfig(monitors={MonitorType.IPI_TLB: []})

    assert MonitorType.IPI_TLB not in config.monitors
