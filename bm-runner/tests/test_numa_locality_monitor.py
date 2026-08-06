# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

import json

from config.benchmark import MonitorType
from monitors.monitor_factory import MonitorFactory
from monitors.numa_locality import NumaLocality


def test_read_counters_filters_vmstat(tmp_path):
    vmstat = tmp_path / "vmstat"
    vmstat.write_text("numa_local 10\nnuma_other 3\nnr_free_pages 99\n")

    assert NumaLocality.read_counters(vmstat) == {"numa_local": 10, "numa_other": 3}


def test_delta_handles_counter_reset():
    assert NumaLocality.delta({"numa_local": 10}, {"numa_local": 4}) == {"numa_local": 0}


def test_ratio_reports_locality_and_hint_faults():
    values = {
        "numa_local": 80,
        "numa_other": 20,
        "numa_hint_faults_local": 30,
        "numa_hint_faults": 40,
    }

    assert NumaLocality.ratio(values, "numa_local", "numa_other") == 80.0
    assert NumaLocality.ratio(values, "numa_hint_faults_local", "numa_hint_faults") == 75.0


def test_collect_reports_global_and_per_node_deltas(tmp_path):
    monitor = NumaLocality(str(tmp_path))
    monitor._samples = [
        {
            "global": {"numa_local": 100, "numa_other": 20},
            "nodes": {"node0": {"numa_local": 60, "numa_other": 5}},
        },
        {
            "global": {"numa_local": 180, "numa_other": 40},
            "nodes": {"node0": {"numa_local": 130, "numa_other": 8}},
        },
    ]

    result = monitor.collect_results()

    assert "numa_local_delta=80;" in result
    assert "numa_other_delta=20;" in result
    assert "numa_local_percent=80.0;" in result
    assert "numa_node0_local_delta=70;" in result
    assert "numa_node0_other_delta=3;" in result


def test_stop_preserves_raw_snapshots(monkeypatch, tmp_path):
    monitor = NumaLocality(str(tmp_path))
    monitor._samples = [{"timestamp": 1.0, "global": {}, "nodes": {}}]
    monkeypatch.setattr(monitor, "sample", lambda: {"timestamp": 2.0, "global": {}, "nodes": {}})

    monitor.stop()

    assert len(json.loads((tmp_path / monitor.OUTPUT_FILE).read_text())) == 2


def test_factory_creates_numa_monitor(monkeypatch, tmp_path):
    monkeypatch.setenv("CSB_ANALYZE", "true")

    monitor = MonitorFactory.create(MonitorType.NUMA_LOCALITY, str(tmp_path), [])

    assert isinstance(monitor, NumaLocality)
