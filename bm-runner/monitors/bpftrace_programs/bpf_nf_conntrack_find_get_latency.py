# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

from monitors.bpf_program import BPFProgram
from monitors.bpf_parser_histograms import BPFParserHistograms

class BPFNfConntrackFindGetLatency(BPFProgram):
    name = "nf_conntrack_find_get_latency"
    parser = BPFParserHistograms()
    program = """
kprobe:__nf_conntrack_find_get
/ __FILTER_CPU__ && __FILTER_PID__ /
{ @start[pid] = nsecs; }

kretprobe:__nf_conntrack_find_get
/ @start[pid] /
{ @ns[pid] = hist(nsecs - @start[pid]); delete(@start[pid]); }
"""
