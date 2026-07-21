#!/usr/bin/env python3
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

"""Remove run-specific process roots and aggregate equal kernel stacks."""

import sys
from collections import defaultdict


totals: dict[str, int] = defaultdict(int)
for line_number, raw in enumerate(sys.stdin, 1):
    line = raw.strip()
    if not line:
        continue
    try:
        stack, count_text = line.rsplit(maxsplit=1)
        count = int(count_text)
    except ValueError as exc:
        raise ValueError(f"line {line_number}: invalid folded stack") from exc
    _, separator, kernel_stack = stack.partition(";")
    totals[kernel_stack if separator else stack] += count

for stack in sorted(totals):
    print(f"{stack} {totals[stack]}")
