# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

import csv
from types import SimpleNamespace

import pytest

from config.benchmark import MonitorType
from monitors.monitor_factory import MonitorFactory
from monitors.scheduler_scalability import SchedulerScalability


RAW = """Attaching 5 probes...
CSB_SCHED|10|worker|1|2|2|1000
CSB_SCHED|10|worker|2|2|3|3000
CSB_SCHED|11|worker|-1|4|4|500
CSB_SCHED_PREEMPTIONS|7
"""


def test_parse_events_preserves_cpu_placement():
    events = SchedulerScalability.parse_events(RAW)

    assert events[0] == {
        "pid": 10,
        "comm": "worker",
        "previous_cpu": 1,
        "target_cpu": 2,
        "run_cpu": 2,
        "latency_ns": 1000,
    }
    assert events[2]["previous_cpu"] == -1


def test_matrix_aggregates_complete_placement_edges():
    rows = SchedulerScalability.aggregate_matrix(SchedulerScalability.parse_events(RAW))

    assert len(rows) == 3
    assert sum(row["count"] for row in rows) == 3
    assert sum(row["migrations"] for row in rows) == 2
    assert sum(row["target_misses"] for row in rows) == 1


def test_write_matrix_preserves_cpu_columns(tmp_path):
    rows = SchedulerScalability.aggregate_matrix(SchedulerScalability.parse_events(RAW))
    path = tmp_path / "matrix.csv"

    SchedulerScalability.write_matrix(rows, str(path))

    parsed = list(csv.DictReader(path.open()))
    assert {"previous_cpu", "target_cpu", "run_cpu"} <= parsed[0].keys()


def test_collect_reports_latency_migration_and_preemption(tmp_path):
    errors = tmp_path / "scheduler.err"
    errors.write_text("lost 2 events")
    monitor = SchedulerScalability.__new__(SchedulerScalability)
    monitor.dir = str(tmp_path)
    monitor.trace = SimpleNamespace(read_output=lambda: RAW, err_file_name=str(errors))

    result = monitor.collect_results()

    assert result == (
        "scheduler_wakeups=3;scheduler_migrations=2;scheduler_target_misses=1;"
        "scheduler_latency_p95_ns=3000;scheduler_preemptions=7;scheduler_lost_events=2;"
    )


def test_program_replaces_target_and_tracks_forks(monkeypatch, tmp_path):
    program = tmp_path / "scheduler.bt"
    program.write_text('x == "__TARGET_COMM__"\nsched_process_fork\n')
    monkeypatch.setattr(SchedulerScalability, "PROGRAM", str(program))

    rendered = SchedulerScalability.program_for_target("worker")

    assert "__TARGET_COMM__" not in rendered
    assert 'x == "worker"' in rendered
    assert "sched_process_fork" in rendered


def test_program_compares_tracepoint_comm_without_str_cast():
    rendered = SchedulerScalability.program_for_target("worker")

    assert 'args->parent_comm == "worker"' in rendered
    assert "str(args->parent_comm)" not in rendered


@pytest.mark.parametrize("target", ["", 'bad"name', "bad\\name", "bad\nname"])
def test_program_rejects_unsafe_target(monkeypatch, tmp_path, target):
    program = tmp_path / "scheduler.bt"
    program.write_text("__TARGET_COMM__")
    monkeypatch.setattr(SchedulerScalability, "PROGRAM", str(program))

    with pytest.raises(ValueError):
        SchedulerScalability.program_for_target(target)


def test_factory_creates_scheduler_monitor(monkeypatch, tmp_path):
    monkeypatch.setenv("CSB_ANALYZE", "true")

    monitor = MonitorFactory.create(MonitorType.SCHEDULER_SCALABILITY, str(tmp_path), ["worker"])

    assert isinstance(monitor, SchedulerScalability)
