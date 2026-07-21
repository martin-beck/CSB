#!/usr/bin/env python3
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

"""Greedily compose candidate folded stacks until they fit a reference profile."""

import argparse
import csv
from collections import Counter
from pathlib import Path


def read_profile(path: Path) -> dict[str, float]:
    counts: dict[str, float] = {}
    for number, raw in enumerate(path.read_text().splitlines(), 1):
        try:
            stack, value = raw.rsplit(maxsplit=1)
            counts[stack] = counts.get(stack, 0.0) + float(value)
        except ValueError as exc:
            raise ValueError(f"{path}:{number}: invalid folded stack") from exc
    total = sum(counts.values())
    if total <= 0:
        raise ValueError(f"{path}: empty profile")
    return {stack: value / total for stack, value in counts.items()}


def closeness(left: dict[str, float], right: dict[str, float]) -> float:
    distance = sum(abs(left.get(key, 0.0) - right.get(key, 0.0)) for key in left | right) / 2
    return 100 * (1 - distance)


def add_average(
    current: dict[str, float], candidate: dict[str, float], rounds: int
) -> dict[str, float]:
    keys = current | candidate
    return {
        key: (current.get(key, 0.0) * rounds + candidate.get(key, 0.0)) / (rounds + 1)
        for key in keys
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--epsilon",
        type=float,
        default=5.0,
        help="stop when the unmatched profile is at most this percentage (default: 5)",
    )
    parser.add_argument("--max-rounds", type=int, default=100)
    args = parser.parse_args()
    if not 0 <= args.epsilon < 100 or args.max_rounds < 1:
        parser.error("epsilon must be in [0, 100) and max-rounds must be positive")

    reference = read_profile(args.reference)
    paths = sorted(args.candidates.glob("*.stacks"))
    if not paths:
        parser.error(f"no .stacks candidates in {args.candidates}")
    candidates = {path.stem.removesuffix(".html"): read_profile(path) for path in paths}
    mixture: dict[str, float] = {}
    selected: Counter[str] = Counter()
    # Accept one candidate even when no stack overlaps, so outputs remain well-defined.
    score = -1.0

    print("round  closeness  residual  candidate")
    for round_number in range(1, args.max_rounds + 1):
        choices = [
            (closeness(reference, add_average(mixture, profile, round_number - 1)), name, profile)
            for name, profile in candidates.items()
        ]
        next_score, name, profile = max(choices, key=lambda item: (item[0], item[1]))
        if next_score <= score + 1e-9:
            print(f"stop   {score:8.2f}%  {100 - score:7.2f}%  no improvement")
            break
        mixture = add_average(mixture, profile, round_number - 1)
        selected[name] += 1
        score = next_score
        print(f"{round_number:5d}  {score:8.2f}%  {100 - score:7.2f}%  {name}")
        if 100 - score <= args.epsilon:
            print(f"stop   {score:8.2f}%  {100 - score:7.2f}%  target reached")
            break
    else:
        print(f"stop   {score:8.2f}%  {100 - score:7.2f}%  round limit")

    args.output.mkdir(parents=True, exist_ok=True)
    total_rounds = sum(selected.values())
    with (args.output / "weights.csv").open("w", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(["benchmark", "weight", "rounds"])
        for name in sorted(selected):
            writer.writerow([name, f"{selected[name] / total_rounds:.8f}", selected[name]])
    reference_samples = max(1, round(sum(read_profile_count(args.reference).values())))
    with (args.output / "fitted.stacks").open("w") as output:
        for stack in sorted(mixture):
            count = round(mixture[stack] * reference_samples)
            if count:
                output.write(f"{stack} {count}\n")


def read_profile_count(path: Path) -> dict[str, float]:
    counts: dict[str, float] = {}
    for raw in path.read_text().splitlines():
        stack, value = raw.rsplit(maxsplit=1)
        counts[stack] = counts.get(stack, 0.0) + float(value)
    return counts


if __name__ == "__main__":
    main()
