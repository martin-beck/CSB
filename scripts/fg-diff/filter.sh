#!/usr/bin/bash
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

set -euo pipefail

file="$1"
target="$2"
outfile="$3"

if [ -z "$1" ] || [ -z "$2" ] || [ -z "$3" ]; then
    echo "usage: $0 input-perf-data-path process-target-regex output-files-path"
    exit 1
fi

"$scriptpath/perf-to-folded.sh" "$file" "$target" "$outfile.stacks" "$outfile.perf-script"
"$FLAMEGRAPH/flamegraph.pl" --width=1920 --title="Flame graph: $(basename "$outfile")" \
    < "$outfile.stacks" > "$outfile"
