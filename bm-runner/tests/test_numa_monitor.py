# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

from monitors.numa import NumaStats


def test_parse_numastat():
    data = NumaStats.parse_numastat("numa_hit 100\nnuma_miss 3\nlocal_node 90\n")

    assert data["numa_hit"] == 100
    assert data["numa_miss"] == 3
    assert data["local_node"] == 90


def test_read_sample_aggregates_nodes(tmp_path):
    node0 = tmp_path / "node0"
    node1 = tmp_path / "node1"
    node0.mkdir()
    node1.mkdir()
    (node0 / "numastat").write_text("numa_hit 10\nnuma_miss 1\n")
    (node1 / "numastat").write_text("numa_hit 20\nnuma_miss 2\n")

    monitor = NumaStats(output_dir="/tmp", args=[str(tmp_path)])
    sample = monitor.read_sample()

    assert sample["numa_numa_hit"] == 30
    assert sample["numa_node0_numa_miss"] == 1
    assert sample["numa_node1_numa_miss"] == 2
    assert sample["numa_node_count"] == 2
