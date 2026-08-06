# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

import pandas as pd


COUNT_FIELD = "container_cnt"
THROUGHPUT_FIELD = "throughput_avg"
EFFICIENCY_FIELD = "scaling_efficiency"
MARGINAL_FIELD = "marginal_throughput"
EFFICIENCY_DERIVATIVE_FIELD = "scaling_efficiency_derivative"
MONITOR_PREFIXES = (
    "psi_",
    "perf_",
    "numa_",
    "scheduler_",
    "ipi_",
    "tlb_",
    "mpstat_",
    "iostat_",
    "sar_",
)


def monitor_fields(frame: pd.DataFrame) -> list[str]:
    """Return numeric monitor outputs suitable for per-operation normalization."""
    return [
        column
        for column in frame.select_dtypes(include="number").columns
        if column.startswith(MONITOR_PREFIXES)
    ]


def add_scaling_derivatives(frame: pd.DataFrame, signals: list[str]) -> pd.DataFrame:
    """Add scaling efficiency and per-operation signal derivatives."""
    result = frame.sort_values(COUNT_FIELD).copy()
    counts = result[COUNT_FIELD]
    throughput = result[THROUGHPUT_FIELD]
    baseline_throughput = throughput.iloc[0]
    result[EFFICIENCY_FIELD] = throughput / baseline_throughput
    result[MARGINAL_FIELD] = throughput.diff() / counts.diff()
    result[EFFICIENCY_DERIVATIVE_FIELD] = result[EFFICIENCY_FIELD].diff() / counts.diff()
    for signal in signals:
        per_operation = f"{signal}_per_operation"
        derivative = f"{signal}_scaling_derivative"
        result[per_operation] = result[signal] / throughput
        result[derivative] = result[per_operation].diff() / counts.diff()
    return result


def rank_signal_correlations(frame: pd.DataFrame, group_fields: list[str]) -> pd.DataFrame:
    """Rank monitor derivatives that move with lost scaling efficiency."""
    rows = []
    derivative_fields = [
        column
        for column in frame.columns
        if column.endswith("_scaling_derivative") and column != EFFICIENCY_DERIVATIVE_FIELD
    ]
    for group_key, group in frame.groupby(group_fields, dropna=False):
        group_key = group_key if isinstance(group_key, tuple) else (group_key,)
        for field in derivative_fields:
            valid = group[[EFFICIENCY_DERIVATIVE_FIELD, field]].dropna()
            if len(valid) < 2:
                continue
            correlation = valid[EFFICIENCY_DERIVATIVE_FIELD].corr(valid[field])
            if pd.isna(correlation):
                continue
            row = {name: value for name, value in zip(group_fields, group_key)}
            row.update(
                {
                    "signal": field.removesuffix("_scaling_derivative"),
                    "correlation": correlation,
                    "absolute_correlation": abs(correlation),
                    "points": len(valid),
                }
            )
            rows.append(row)
    if not rows:
        return pd.DataFrame(
            columns=group_fields + ["signal", "correlation", "absolute_correlation", "points"]
        )
    return pd.DataFrame(rows).sort_values("absolute_correlation", ascending=False)
