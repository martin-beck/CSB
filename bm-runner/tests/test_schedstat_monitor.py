# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

from monitors.schedstat import SchedstatStats


def test_parse_schedstat_aggregates_cpu_lines():
    data = SchedstatStats.parse_schedstat(
        "version 15\n"
        "cpu0 0 0 0 0 0 0 100 20 4\n"
        "domain0 0001 0 0 0\n"
        "cpu1 0 0 0 0 0 0 200 30 6\n"
    )

    assert data["schedstat_cpu_time_ns"] == 300
    assert data["schedstat_run_delay_ns"] == 50
    assert data["schedstat_timeslices"] == 10
    assert data["schedstat_cpu_count"] == 2


def test_delta_keeps_cpu_count_as_value():
    start = {"schedstat_run_delay_ns": 10, "schedstat_cpu_count": 2}
    stop = {"schedstat_run_delay_ns": 25, "schedstat_cpu_count": 2}

    assert SchedstatStats.delta(start, stop) == {
        "schedstat_run_delay_ns_delta": 15,
        "schedstat_cpu_count": 2,
    }
