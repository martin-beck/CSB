# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

import csv
from types import SimpleNamespace

import pytest

from config.benchmark import MonitorType
from monitors.monitor_factory import MonitorFactory
from monitors.offcpu import OffCpu


RAW_EVENTS = """Attaching 6 probes...
CSB_OFFCPU_BEGIN|11|worker|21|waker|1000|700|300
    sleep_leaf+1
    sleep_parent+2
CSB_WAKER_STACK
    wake_leaf+3
    wake_parent+4
CSB_OFFCPU_END
CSB_OFFCPU_BEGIN|12|worker|22|waker|3000|2000|1000
    sleep_leaf+1
    sleep_parent+2
CSB_WAKER_STACK
    wake_leaf+3
    wake_parent+4
CSB_OFFCPU_END
CSB_OFFCPU_BEGIN|13|worker|0|unknown|500|500|0
    other_leaf+5
CSB_WAKER_STACK
unknown
CSB_OFFCPU_END
"""


def test_parse_events_preserves_complete_edges():
    events = OffCpu.parse_events(RAW_EVENTS)

    assert len(events) == 3
    assert events[0] == {
        "sleeper_pid": 11,
        "sleeper_comm": "worker",
        "waker_pid": 21,
        "waker_comm": "waker",
        "offcpu_ns": 1000,
        "sleep_ns": 700,
        "runq_ns": 300,
        "sleeper_stack": "sleep_parent+2;sleep_leaf+1",
        "waker_stack": "wake_parent+4;wake_leaf+3",
    }
    assert events[2]["waker_stack"] == "unknown"


def test_aggregate_matrix_combines_identical_stack_pairs():
    rows = OffCpu.aggregate_matrix(OffCpu.parse_events(RAW_EVENTS))

    assert len(rows) == 2
    assert rows[0]["count"] == 2
    assert rows[0]["total_offcpu_ns"] == 4000
    assert rows[0]["total_sleep_ns"] == 2700
    assert rows[0]["total_runq_ns"] == 1300
    assert rows[0]["p95_offcpu_ns"] == 3000
    assert rows[0]["max_offcpu_ns"] == 3000


def test_write_matrix_preserves_stack_columns(tmp_path):
    path = tmp_path / "matrix.csv"
    rows = OffCpu.aggregate_matrix(OffCpu.parse_events(RAW_EVENTS))

    OffCpu.write_matrix(rows, str(path))

    parsed = list(csv.DictReader(path.open()))
    assert len(parsed) == 2
    assert parsed[0]["sleeper_stack"] == "sleep_parent+2;sleep_leaf+1"
    assert parsed[0]["waker_stack"] == "wake_parent+4;wake_leaf+3"


def test_collect_results_reports_matrix_latency_and_loss(tmp_path):
    output = tmp_path / OffCpu.RAW_FILE
    errors = tmp_path / OffCpu.ERROR_FILE
    output.write_text(RAW_EVENTS)
    errors.write_text("lost 4 events\ndropped 2 events\n")
    monitor = OffCpu.__new__(OffCpu)
    monitor.dir = str(tmp_path)
    monitor.trace = SimpleNamespace(
        read_output=lambda: output.read_text(), err_file_name=str(errors)
    )

    result = monitor.collect_results()

    assert result == (
        "offcpu_events=3;offcpu_matrix_edges=2;offcpu_total_ns=4500;"
        "offcpu_p95_ns=3000;offcpu_runq_p95_ns=1000;offcpu_lost_events=6;"
    )
    assert (tmp_path / OffCpu.MATRIX_FILE).is_file()


def test_program_replaces_target_and_tracks_forks(monkeypatch, tmp_path):
    program = tmp_path / "offcpu.bt"
    program.write_text('x == "__TARGET_COMM__"\nsched_process_fork\n')
    monkeypatch.setattr(OffCpu, "PROGRAM", str(program))

    rendered = OffCpu.program_for_target("worker")

    assert "__TARGET_COMM__" not in rendered
    assert 'x == "worker"' in rendered
    assert "sched_process_fork" in rendered


def test_program_compares_tracepoint_comm_without_str_cast():
    rendered = OffCpu.program_for_target("worker")

    assert 'args->parent_comm == "worker"' in rendered
    assert "str(args->parent_comm)" not in rendered


@pytest.mark.parametrize("target", ["", 'bad"name', "bad\\name", "bad\nname"])
def test_program_rejects_unsafe_target(monkeypatch, tmp_path, target):
    program = tmp_path / "offcpu.bt"
    program.write_text("__TARGET_COMM__")
    monkeypatch.setattr(OffCpu, "PROGRAM", str(program))

    with pytest.raises(ValueError):
        OffCpu.program_for_target(target)


def test_lost_event_parser():
    assert OffCpu.parse_lost_events("Lost 3 events; dropped 7 events") == 10


def test_factory_creates_offcpu_monitor(monkeypatch, tmp_path):
    monkeypatch.setenv("CSB_ANALYZE", "true")
    monitor = MonitorFactory.create(MonitorType.OFFCPU, str(tmp_path), ["worker"])

    assert isinstance(monitor, OffCpu)
    assert monitor.trace.cmds[:3] == ["sudo", "bpftrace", "-e"]
