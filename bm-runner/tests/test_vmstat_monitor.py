# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

from monitors.vmstat import VmstatStats


def test_parse_vmstat():
    data = VmstatStats.parse_vmstat("pgfault 100\npgmajfault 2\nnr_dirty 7\n")

    assert data["pgfault"] == 100
    assert data["pgmajfault"] == 2
    assert data["nr_dirty"] == 7


def test_filter_and_delta():
    monitor = VmstatStats(output_dir="/tmp", args=[])
    sample = monitor.filter_sample({"pgfault": 100, "nr_free_pages": 20, "numa_hit": 5})

    assert sample == {"vmstat_pgfault": 100, "vmstat_numa_hit": 5}
    assert VmstatStats.delta({"vmstat_pgfault": 40}, sample)["vmstat_pgfault_delta"] == 60
