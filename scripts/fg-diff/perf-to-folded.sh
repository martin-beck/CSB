#!/usr/bin/bash
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

# Symbolize kernel-only samples now so they remain usable without the original kernel.
set -euo pipefail

if [ "$#" -ne 4 ]; then
    echo "usage: $0 PERF_DATA PROCESS_REGEX OUTPUT_STACKS OUTPUT_PERF_SCRIPT" >&2
    exit 2
fi

perf_data=$1
target=$2
output=$3
perf_script=$4
root=$(cd "$(dirname "$0")/../.." && pwd)
flamegraph=${FLAMEGRAPH:-$root/deps/FlameGraph}
allowed_tids=""
if [[ "$target" == tgid:* ]]; then
    allowed_tids=$("$root/scripts/fg-diff/resolve-perf-tids.sh" "$perf_data" "${target#tgid:}")
fi
if [ -n "${PERF:-}" ]; then perf_cmd=("$PERF"); else perf_cmd=(sudo perf); fi

"${perf_cmd[@]}" script -i "$perf_data" --dsos='[kernel.kallsyms]' > "$perf_script"
awk -v target="$target" -v allowed_csv="$allowed_tids" '
    BEGIN {
        split(allowed_csv, tids, ",")
        for (i in tids) allowed[tids[i]] = 1
    }
    $NF == "cycles:" || $NF == "cycles:P:" || $NF == "cpu-clock:" || $NF ~ /\/cycles\/:$/ {
        emit = (allowed_csv != "" ? ($2 in allowed) : ($1 ~ target))
        if (emit) { $1 = "THR"; print }
        next
    }
    emit && NF == 0 { emit = 0; print; next }
    emit && $NF == "([kernel.kallsyms])" { print }
' "$perf_script" | "$flamegraph/stackcollapse-perf.pl" | \
    "$root/scripts/fg-diff/canonicalize-folded.py" > "$output"

if [ ! -s "$output" ]; then
    echo "no kernel stacks matched process selector: $target" >&2
    exit 1
fi
