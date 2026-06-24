# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

from monitors.bpf_program import BPFProgram
from monitors.bpf_parser_histograms import BPFParserHistograms

class BPFJbd2LogWaitForSpace(BPFProgram):
    name = "jbd2_log_wait_for_space"
    parser = BPFParserHistograms()
    program = """
kprobe:__jbd2_log_wait_for_space
/ __FILTER_CPU__ && __FILTER_PID__ /
{ @start[pid] = nsecs; }

kretprobe:__jbd2_log_wait_for_space
/ @start[pid] /
{ @ns[pid] = hist(nsecs - @start[pid]); delete(@start[pid]); }
"""
