# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

from monitors.bpf_program import BPFProgram
from monitors.bpf_parser_histograms import BPFParserHistograms


class BPFVfsWriteLatency(BPFProgram):
    name = "vfs_write_latency"
    parser = BPFParserHistograms()
    program = """
kprobe:vfs_write
/ __FILTER_CPU__ && __FILTER_PID__ /
{ @start[pid] = nsecs; }

kretprobe:vfs_write
/ @start[pid] /
{ @ns[pid] = hist(nsecs - @start[pid]); delete(@start[pid]); }
"""
