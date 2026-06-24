# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

from monitors.bpf_program import BPFProgram
from monitors.bpf_parser_histograms import BPFParserHistograms

class BPFCGroupRstatLockContAlias(BPFProgram):
    name = "cgroup_rstat_lock_cont"
    parser = BPFParserHistograms()
    program = """
kprobe:cgroup_rstat_flush_hold
/ __FILTER_CPU__ && __FILTER_PID__ /
{ @start[pid] = nsecs; }

kretprobe:cgroup_rstat_flush_hold
/ @start[pid] /
{ @ns[pid] = hist(nsecs - @start[pid]); delete(@start[pid]); }
"""
