# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

import pandas as pd

import analyze
from scaling_derivative import (
    EFFICIENCY_DERIVATIVE_FIELD,
    add_scaling_derivatives,
    monitor_fields,
    rank_signal_correlations,
)


def test_monitor_fields_selects_numeric_monitor_outputs():
    frame = pd.DataFrame(
        {
            "psi_cpu_total": [1],
            "scheduler_migrations": [2],
            "container_cnt": [1],
            "hostname": ["host"],
        }
    )

    assert monitor_fields(frame) == ["psi_cpu_total", "scheduler_migrations"]


def test_add_scaling_derivatives_normalizes_per_operation():
    frame = pd.DataFrame(
        {
            "container_cnt": [1, 2, 4],
            "throughput_avg": [100.0, 90.0, 70.0],
            "scheduler_migrations": [10.0, 18.0, 28.0],
        }
    )

    result = add_scaling_derivatives(frame, ["scheduler_migrations"])

    assert result["scaling_efficiency"].tolist() == [1.0, 0.9, 0.7]
    assert result["marginal_throughput"].iloc[1] == -10.0
    assert result["scheduler_migrations_per_operation"].tolist() == [0.1, 0.2, 0.4]
    assert result["scheduler_migrations_scaling_derivative"].iloc[2] == 0.1


def test_rank_signals_correlated_with_efficiency_loss():
    frame = pd.DataFrame(
        {
            "benchmark": ["bm"] * 4,
            EFFICIENCY_DERIVATIVE_FIELD: [None, -0.1, -0.2, -0.3],
            "ipi_sends_scaling_derivative": [None, 1.0, 2.0, 3.0],
            "noise_scaling_derivative": [None, 2.0, 1.0, 2.0],
        }
    )

    ranking = rank_signal_correlations(frame, ["benchmark"])

    assert ranking.iloc[0]["signal"] == "ipi_sends"
    assert ranking.iloc[0]["absolute_correlation"] == 1.0
    assert ranking.iloc[0]["points"] == 3


def test_rank_signals_returns_stable_empty_schema():
    frame = pd.DataFrame({"benchmark": ["bm"], EFFICIENCY_DERIVATIVE_FIELD: [None]})

    ranking = rank_signal_correlations(frame, ["benchmark"])

    assert list(ranking.columns) == [
        "benchmark",
        "signal",
        "correlation",
        "absolute_correlation",
        "points",
    ]


def test_analyze_transform_carries_monitor_derivatives(monkeypatch):
    frame = pd.DataFrame(
        {
            "algo_name": ["bm"] * 3,
            "execution_type": ["native"] * 3,
            "hostname": ["host"] * 3,
            "kernel": ["kernel"] * 3,
            "nb_threads": [1] * 3,
            "container_cnt": [1, 2, 4],
            "throughput_min": [100.0, 90.0, 70.0],
            "univ_succ_percent": [100.0] * 3,
            "ipi_sends": [10.0, 18.0, 28.0],
        }
    )
    monkeypatch.setattr(analyze, "read_data_frame_from_csv", lambda path: frame)

    transformed = analyze.transform("ignored.csv")[0]

    assert transformed["scaling_efficiency"].tolist() == [1.0, 0.9, 0.7]
    assert "ipi_sends_per_operation" in transformed
    assert "ipi_sends_scaling_derivative" in transformed
