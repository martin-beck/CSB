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
STATE_DIR="$(create_state_dir)"
trap 'jobs -pr | xargs -r kill 2>/dev/null || true; cleanup_cgroups "${ROOT}"; cleanup_state "${STATE_DIR}"' EXIT

START_NS="$(date +%s%N)"
DEADLINE="$(deadline_ns)"
PIDS=()

make_tree() {
    local leaves="${INITIAL_SIZE}"
    local i
    for i in $(seq 1 "${leaves}"); do
        mkdir -p "${ROOT}/grp-${i}/leaf"
    done
}

stat_worker() {
    local id="$1"
    local ops=0
    local failures=0
    local cg

    while before_deadline "${DEADLINE}"; do
        for cg in "${ROOT}"/grp-*/leaf; do
            [ -d "${cg}" ] || continue
            cat "${cg}/cgroup.stat" "${cg}/cpu.stat" >/dev/null 2>&1 || failures=$((failures + 1))
            [ -f "${cg}/memory.stat" ] && cat "${cg}/memory.stat" >/dev/null 2>&1 || true
            ops=$((ops + 1))
            burn_noise
        done
    done

    printf '%s %s\n' "${ops}" "${failures}" > "${STATE_DIR}/stat-${id}.out"
}

cpu_worker() {
    local id="$1"
    local cg="${ROOT}/grp-$((id % INITIAL_SIZE + 1))/leaf"
    printf '%s\n' "${BASHPID}" > "${cg}/cgroup.procs" 2>/dev/null || true
    while before_deadline "${DEADLINE}"; do
        :
    done
}

make_tree

for id in $(seq 1 "${THREADS}"); do
    cpu_worker "${id}" &
    PIDS+=("$!")
    stat_worker "${id}" &
    PIDS+=("$!")
done

for pid in "${PIDS[@]}"; do
    wait "${pid}"
done

OPS="$(awk '{ ops += $1 } END { print ops + 0 }' "${STATE_DIR}"/stat-*.out)"
FAILURES="$(awk '{ failures += $2 } END { print failures + 0 }' "${STATE_DIR}"/stat-*.out)"
ELAPSED_NS="$(($(date +%s%N) - START_NS))"

metric_line "${OPS}" "${FAILURES}" "${ELAPSED_NS}" "cgroups=${INITIAL_SIZE};"
