# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

from pathlib import Path
from unittest.mock import patch

from monitors.perflock import PerfLock


CALLERS = """1;100;100;100;mutex;wait_one
2;600;400;300;spinlock;wait_two
"""
IDENTITIES = """2; 600; 400; 300; 0xffff0001; lock_hot; spinlock
1; 100; 100; 100; 0xffff0002; lock_cold; mutex
"""


def test_collect_results_reports_lock_identity(monkeypatch, tmp_path):
    monitor = PerfLock(str(tmp_path))
    Path(monitor.perf_contention_csv).write_text(CALLERS)
    Path(monitor.perf_identity_csv).write_text(IDENTITIES)
    monkeypatch.setattr(monitor, "_PerfLock__run_lock_contention", lambda *args, **kwargs: True)
    monkeypatch.setattr(monitor, "_PerfLock__plot", lambda data: None)
    monkeypatch.setattr(monitor, "_PerfLock__plot_identities", lambda data: None)

    result = monitor.collect_results()

    assert "perf_lock_unique_locks=2;" in result
    assert "perf_lock_hottest_address=0xffff0001;" in result
    assert "perf_lock_hottest_symbol=lock_hot;" in result
    assert "perf_lock_hottest_total_wait=600;" in result


def test_identity_report_requests_lock_addresses(tmp_path):
    monitor = PerfLock(str(tmp_path))
    (tmp_path / "perf.data").touch()
    run_report = getattr(monitor, "_PerfLock__run_lock_contention")

    with patch("monitors.perflock.shell_out") as shell:
        assert run_report(monitor.perf_identity_csv, lock_identity=True)

    command = shell.call_args.kwargs["command"]
    assert "--lock-addr" in command
    assert command[command.index("--output") + 1] == monitor.perf_identity_csv


def test_caller_report_does_not_request_lock_addresses(tmp_path):
    monitor = PerfLock(str(tmp_path))
    (tmp_path / "perf.data").touch()
    run_report = getattr(monitor, "_PerfLock__run_lock_contention")

    with patch("monitors.perflock.shell_out") as shell:
        assert run_report(monitor.perf_contention_csv)

    assert "--lock-addr" not in shell.call_args.kwargs["command"]


def test_identity_report_requires_perf_data(tmp_path):
    monitor = PerfLock(str(tmp_path))
    run_report = getattr(monitor, "_PerfLock__run_lock_contention")

    with patch("monitors.perflock.shell_out") as shell:
        assert not run_report(monitor.perf_identity_csv, lock_identity=True)

    shell.assert_not_called()
