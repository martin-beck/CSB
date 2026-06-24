# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

from monitors.bpf_program import BPFProgram
from monitors.bpf_parser_histograms import BPFParserHistograms

class BPFCGroupKnLockLive(BPFProgram):
    name = "cgroup_kn_lock_live"
    parser = BPFParserHistograms()
    program = """
kprobe:cgroup_kn_lock_live
/ __FILTER_CPU__ && __FILTER_PID__ /
{ @start[pid] = nsecs; }

kretprobe:cgroup_kn_lock_live
/ @start[pid] /
{ @lock_live_latency[pid] = hist(nsecs - @start[pid]); delete(@start[pid]); }
"""
