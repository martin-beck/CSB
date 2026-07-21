#!/usr/bin/bash
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

# Resolve all recorded thread IDs belonging to the first matching root process.
set -euo pipefail
if [ "$#" -ne 2 ]; then
    echo "usage: $0 PERF_DATA ROOT_COMM" >&2
    exit 2
fi
if [ -n "${PERF:-}" ]; then perf_cmd=("$PERF"); else perf_cmd=(sudo perf); fi
"${perf_cmd[@]}" script -i "$1" --show-task-events 2>/dev/null | \
    sed -nE 's/.*PERF_RECORD_COMM: ([^:]+):([0-9]+)\/([0-9]+).*/\1 \2 \3/p' | \
    awk -v root="$2" '
        $1 == root && root_tgid == "" { root_tgid = $2 }
        { tgids[NR] = $2; tids[NR] = $3 }
        END {
            if (root_tgid == "") exit 1
            for (i = 1; i <= NR; i++) {
                if (tgids[i] == root_tgid) {
                    printf "%s%s", separator, tids[i]
                    separator = ","
                }
            }
            print ""
        }'
