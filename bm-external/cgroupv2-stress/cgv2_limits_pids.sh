#!/usr/bin/env bash
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=cgv2_common.sh
. "${SCRIPT_DIR}/cgv2_common.sh"

parse_common_args "$@"
require_cgroup2

ROOT="$(create_bench_root)"
trap 'jobs -pr | xargs -r kill 2>/dev/null || true; cleanup_cgroups "${ROOT}"' EXIT

if ! [ -f "${ROOT}/pids.max" ]; then
    echo "pids controller is not available in ${ROOT}" >&2
    exit 1
fi

START_NS="$(date +%s%N)"
DEADLINE="$(deadline_ns)"
OPS=0
FAILURES=0
LIMIT="${INITIAL_SIZE}"

while before_deadline "${DEADLINE}"; do
    CG="${ROOT}/limit-${OPS}"
    if ! mkdir "${CG}" 2>/dev/null; then
        FAILURES=$((FAILURES + 1))
        continue
    fi

    printf '%s\n' "${LIMIT}" > "${CG}/pids.max" 2>/dev/null || FAILURES=$((FAILURES + 1))
    CHILDREN=()
    for _ in $(seq 1 "$((LIMIT + THREADS))"); do
        (
            printf '%s\n' "${BASHPID}" > "${CG}/cgroup.procs" 2>/dev/null || exit 1
            sleep 0.05
        ) &
        CHILDREN+=("$!")
        burn_noise
    done

    for pid in "${CHILDREN[@]}"; do
        if wait "${pid}" 2>/dev/null; then
            OPS=$((OPS + 1))
        else
            FAILURES=$((FAILURES + 1))
        fi
    done

    rmdir "${CG}" 2>/dev/null || true
done

ELAPSED_NS="$(($(date +%s%N) - START_NS))"
metric_line "${OPS}" "${FAILURES}" "${ELAPSED_NS}" "limit=${LIMIT};"
