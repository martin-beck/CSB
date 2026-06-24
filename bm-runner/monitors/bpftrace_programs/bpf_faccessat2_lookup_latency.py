# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

from monitors.bpf_program import BPFProgram
from monitors.bpf_parser_histograms import BPFParserHistograms

class BPFFaccessat2LookupLatency(BPFProgram):
    name = "faccessat2_lookup_latency"
    parser = BPFParserHistograms()
    program = """
kprobe:do_faccessat
/ __FILTER_CPU__ && __FILTER_PID__ /
{ @start[pid] = nsecs; }

kretprobe:do_faccessat
/ @start[pid] /
{ @do_faccessat_ns[pid] = hist(nsecs - @start[pid]); delete(@start[pid]); }
"""
