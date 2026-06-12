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

enable_cgroup_controller "${ROOT}" "memory"

START_NS="$(date +%s%N)"
DEADLINE="$(deadline_ns)"
OPS=0
FAILURES=0
EVENTS_HIGH_START="$(awk '$1 == "high" { print $2 + 0 }' "${ROOT}/memory.events")"
EVENTS_OOM_START="$(awk '$1 == "oom" { print $2 + 0 }' "${ROOT}/memory.events")"
WORKERS=()
LIMIT_BYTES="$((INITIAL_SIZE * 1024 * 1024))"

alloc_worker() {
    local id="$1"
    local cg="${ROOT}/mem-${id}"
    mkdir "${cg}"
    require_controller_file "${cg}" "memory" "memory.high"
    printf '%s\n' "${BASHPID}" > "${cg}/cgroup.procs" 2>/dev/null || true
    printf '%s\n' "${LIMIT_BYTES}" > "${cg}/memory.high" 2>/dev/null || true
    printf '%s\n' "$((LIMIT_BYTES * 4))" > "${cg}/memory.max" 2>/dev/null || true

    python3 - "${DURATION}" "${INITIAL_SIZE}" "${NOISE}" <<'PY'
import sys
import time

duration = int(sys.argv[1])
mb = int(sys.argv[2])
noise = int(sys.argv[3])
deadline = time.monotonic() + duration
ops = 0
bufs = []

while time.monotonic() < deadline:
    bufs.append(bytearray(1024 * 1024))
    bufs[-1][0] = 1
    ops += 1
    if len(bufs) >= max(2, mb * 3):
        del bufs[:max(1, mb)]
    for _ in range(noise):
        pass

print(ops)
PY
}

for id in $(seq 1 "${THREADS}"); do
    if alloc_worker "${id}" > "${STATE_DIR}/worker-${id}.out" & then
        WORKERS+=("$!")
    else
        FAILURES=$((FAILURES + 1))
    fi
done

for pid in "${WORKERS[@]}"; do
    if ! wait "${pid}"; then
        FAILURES=$((FAILURES + 1))
    fi
done

OPS="$(awk '{ ops += $1 } END { print ops + 0 }' "${STATE_DIR}"/worker-*.out)"
EVENTS_HIGH_END="$(awk '$1 == "high" { print $2 + 0 }' "${ROOT}/memory.events")"
EVENTS_OOM_END="$(awk '$1 == "oom" { print $2 + 0 }' "${ROOT}/memory.events")"
ELAPSED_NS="$(($(date +%s%N) - START_NS))"

metric_line "${OPS}" "${FAILURES}" "${ELAPSED_NS}" "memory_high_events=$((EVENTS_HIGH_END - EVENTS_HIGH_START));memory_oom_events=$((EVENTS_OOM_END - EVENTS_OOM_START));limit_bytes=${LIMIT_BYTES};"
