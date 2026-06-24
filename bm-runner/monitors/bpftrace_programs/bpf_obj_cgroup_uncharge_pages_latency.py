# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

from monitors.bpf_program import BPFProgram
from monitors.bpf_parser_histograms import BPFParserHistograms

class BPFObjCgroupUnchargePagesLatency(BPFProgram):
    name = "obj_cgroup_uncharge_pages_latency"
    parser = BPFParserHistograms()
    program = """
kprobe:obj_cgroup_uncharge_pages
/ __FILTER_CPU__ && __FILTER_PID__ /
{ @start[pid] = nsecs; }

kretprobe:obj_cgroup_uncharge_pages
/ @start[pid] /
{ @ns[pid] = hist(nsecs - @start[pid]); delete(@start[pid]); }
"""
