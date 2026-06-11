# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

from monitors.pidstat import PidstatStats


def test_aggregate_output_averages_numeric_columns():
    output = (
        "Linux 6.6.0 (host)\n\n"
        "UID TGID TID %usr %system cswch/s nvcswch/s Command\n"
        "1000 10 - 1.00 2.00 3.00 4.00 bench\n"
        "1000 - 11 3.00 4.00 5.00 6.00 bench\n"
    )

    data = PidstatStats.aggregate_output(output)

    assert data["pidstat_pct_usr_avg"] == 2.0
    assert data["pidstat_pct_system_avg"] == 3.0
    assert data["pidstat_cswch_per_s_avg"] == 4.0
    assert data["pidstat_nvcswch_per_s_avg"] == 5.0


def test_aggregate_output_handles_timestamp_prefix():
    output = (
        "12:00:01 UID PID minflt/s majflt/s Command\n"
        "12:00:02 1000 10 8.00 1.00 bench\n"
    )

    assert PidstatStats.aggregate_output(output) == {
        "pidstat_minflt_per_s_avg": 8.0,
        "pidstat_majflt_per_s_avg": 1.0,
    }
