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
trap 'cleanup_cgroups "${ROOT}"; cleanup_state "${STATE_DIR}"' EXIT

START_NS="$(date +%s%N)"
DEADLINE="$(deadline_ns)"
PIDS=()

worker() {
    local id="$1"
    local ops=0
    local failures=0
    local batch="${INITIAL_SIZE}"
    local cg path i child

    while before_deadline "${DEADLINE}"; do
        i=0
        while [ "${i}" -lt "${batch}" ]; do
            cg="${ROOT}/w${id}-${ops}-${i}"
            if mkdir "${cg}" 2>/dev/null; then
                (:) &
                child="$!"
                printf '%s\n' "${child}" > "${cg}/cgroup.procs" 2>/dev/null || failures=$((failures + 1))
                wait "${child}" 2>/dev/null || true
                ops=$((ops + 1))
            else
                failures=$((failures + 1))
            fi
            i=$((i + 1))
            burn_noise
        done

        for path in "${ROOT}"/w"${id}"-*; do
            [ -d "${path}" ] || continue
            rmdir "${path}" 2>/dev/null || failures=$((failures + 1))
        done
    done

    printf '%s %s\n' "${ops}" "${failures}" > "${STATE_DIR}/worker-${id}.out"
}

for id in $(seq 1 "${THREADS}"); do
    worker "${id}" &
    PIDS+=("$!")
done

for pid in "${PIDS[@]}"; do
    wait "${pid}"
done

OPS="$(awk '{ ops += $1 } END { print ops + 0 }' "${STATE_DIR}"/worker-*.out)"
FAILURES="$(awk '{ failures += $2 } END { print failures + 0 }' "${STATE_DIR}"/worker-*.out)"
ELAPSED_NS="$(($(date +%s%N) - START_NS))"

metric_line "${OPS}" "${FAILURES}" "${ELAPSED_NS}"
