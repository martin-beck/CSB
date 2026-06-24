# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

from monitors.bpf_program import BPFProgram
from monitors.bpf_parser_histograms import BPFParserHistograms


class BPFExt4TruncateWritebackLatency(BPFProgram):
    name = "ext4_truncate_writeback_latency"
    parser = BPFParserHistograms()
    program = """
kprobe:ext4_truncate
/ __FILTER_CPU__ && __FILTER_PID__ /
{ @start[pid] = nsecs; }

kretprobe:ext4_truncate
/ @start[pid] /
{ @ns[pid] = hist(nsecs - @start[pid]); delete(@start[pid]); }
"""
