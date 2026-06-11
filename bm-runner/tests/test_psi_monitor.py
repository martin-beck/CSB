# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

from monitors.psi import PressureStallStats


def test_parse_pressure():
    data = PressureStallStats.parse_pressure(
        "some avg10=1.23 avg60=0.50 avg300=0.10 total=100\n"
        "full avg10=0.00 avg60=0.00 avg300=0.00 total=25\n"
    )

    assert data["some"]["avg10"] == 1.23
    assert data["some"]["total"] == 100
    assert data["full"]["total"] == 25


def test_flatten_delta_uses_total_delta_and_stop_averages():
    start = {"cpu": {"some": {"avg10": 0.10, "total": 100.0}}}
    stop = {"cpu": {"some": {"avg10": 0.25, "total": 140.0}}}

    assert PressureStallStats.flatten_delta(start, stop) == {
        "psi_cpu_some_avg10": 0.25,
        "psi_cpu_some_total_delta": 40.0,
    }
