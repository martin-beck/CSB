#!/usr/bin/bash
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

# Fit a weighted candidate mixture; keep stdout limited to round-by-round progress.
set -euo pipefail
if [ "$#" -lt 3 ]; then
    echo "usage: $0 REFERENCE_STACKS CANDIDATE_DIR OUTPUT_DIR [FIT_OPTIONS ...]" >&2
    exit 2
fi
reference=$1; candidates=$2; output=$3; shift 3
if [ -e "$output" ]; then
    echo "output already exists: $output" >&2
    exit 1
fi
script_dir=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$output"
"$script_dir/fit.py" --reference "$reference" --candidates "$candidates" \
    --output "$output" "$@" | tee "$output/progress.log"

root=$(cd "$script_dir/../.." && pwd)
flamegraph=${FLAMEGRAPH:-$root/deps/FlameGraph}
if [ -x "$flamegraph/flamegraph.pl" ]; then
    "$flamegraph/flamegraph.pl" --width=1920 --title="Fitted benchmark mixture" \
        < "$output/fitted.stacks" > "$output/fitted.html"
fi
echo "result weights: $output/weights.csv"
