# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

from monitors.slabinfo import SlabinfoStats


def test_parse_slabinfo():
    data = SlabinfoStats.parse_slabinfo(
        "slabinfo - version: 2.1\n"
        "# name active_objs num_objs\n"
        "dentry 10 20 0 0 0\n"
        "inode_cache 3 5 0 0 0\n"
    )

    assert data["dentry"]["active_objs"] == 10
    assert data["dentry"]["num_objs"] == 20
    assert data["inode_cache"]["active_objs"] == 3


def test_filter_sample_and_delta():
    monitor = SlabinfoStats(output_dir="/tmp", args=[])
    sample = monitor.filter_sample(
        {
            "dentry": {"active_objs": 10, "num_objs": 20},
            "other_cache": {"active_objs": 1, "num_objs": 2},
        }
    )

    assert sample["slabinfo_active_objs"] == 11
    assert sample["slabinfo_num_objs"] == 22
    assert sample["slabinfo_dentry_active_objs"] == 10
    assert (
        SlabinfoStats.delta({"slabinfo_active_objs": 5}, sample)[
            "slabinfo_active_objs_delta"
        ]
        == 6
    )
