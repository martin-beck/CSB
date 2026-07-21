#!/usr/bin/bash
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

# Collect the trace and symbolized kernel profile needed to fit benchmarks on another host.
set -euo pipefail

usage() {
    echo "usage: $0 --output DIR [--target REGEX] -- COMMAND [ARG ...]"
}

output=""
target=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        --output) output="$2"; shift 2 ;;
        --target) target="$2"; shift 2 ;;
        --) shift; break ;;
        *) usage >&2; exit 2 ;;
    esac
done
if [ -z "$output" ] || [ "$#" -eq 0 ]; then
    usage >&2
    exit 2
fi
if [ -e "$output" ]; then
    echo "output already exists: $output" >&2
    exit 1
fi

script_dir=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$script_dir/../.." && pwd)
target=${target:-$(basename "$1" | cut -c1-15)}
mkdir -p "$output"

printf '%q ' "$@" > "$output/command.txt"
printf '\n' >> "$output/command.txt"
{
    echo "csb.capture.date=$(date --iso-8601=seconds)"
    echo "csb.capture.uname=$(uname -a)"
    echo "csb.capture.target=$target"
    echo "csb.capture.perf_version=$(${PERF:-perf} version)"
} > "$output/capture.meta"

echo "[1/3] collecting syscall trace"
"$root/scripts/plugins/collect_strace.sh" "$output/trace.strace" "$@"

echo "[2/3] collecting untraced kernel profile"
"${PERF:-perf}" record -o "$output/perf.data" -g -- "$@"

echo "[3/3] symbolizing portable kernel stacks"
"$root/scripts/fg-diff/perf-to-folded.sh" "$output/perf.data" "$target" \
    "$output/reference.stacks" "$output/perf.script"
echo "capture ready: $output"
