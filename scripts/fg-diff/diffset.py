#!/usr/bin/python3
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

import argparse
import csv
import pathlib


def process(result_file, cutoff):
    with result_file.open(newline="") as source:
        rows = [row for row in csv.reader(source) if row and not row[0].startswith("#")]
    selected = {row[0] for row in rows}
    for left, right, difference, *_ in sorted(rows):
        if left != right and left in selected and float(difference) < cutoff:
            selected.discard(right)
    return selected


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Filter benchmarks based on the similarity of the flame graphs"
    )
    parser.add_argument(
        "--cutoff",
        help="The benchmarks with maximum stack difference below this percentage will be considered the same.",
        type=float,
    )
    parser.add_argument(
        "--input",
        help="Path to the input csv file.",
        type=pathlib.Path,
        required=True,
    )
    (args, unknown_args) = parser.parse_known_args()
    s = process(args.input, args.cutoff)
    for i in sorted(s):
        print(i.removesuffix(".html.stacks"))
