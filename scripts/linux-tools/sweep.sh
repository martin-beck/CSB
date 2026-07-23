#!/usr/bin/env bash
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT
set -Eeuo pipefail
source "$(cd -- "$(dirname -- "$0")" && pwd)/lib/common.sh"
usage() { printf 'usage: %s [--trace|--no-trace|--plan] [--run micro|small|all] [--duration SECONDS]\n' "$0"; }
mode=--plan; run_set=all; duration="${DURATION:-10}"
while (($#)); do
  case "$1" in
    --trace|--no-trace|--plan) mode="$1"; shift ;;
    --run) [[ $# -ge 2 ]] || { usage; exit 2; }; run_set="$2"; shift 2 ;;
    --duration) [[ $# -ge 2 ]] || { usage; exit 2; }; duration="$2"; shift 2 ;;
    *) usage; exit 2 ;;
  esac
done
[[ "${run_set}" =~ ^(micro|small|all)$ ]] || die 'expected --run micro, small, or all'
[[ "${duration}" =~ ^[1-9][0-9]*$ ]] || die 'duration must be a positive integer'
workloads=(micro small); [[ "${run_set}" != all ]] && workloads=("${run_set}")
failures=0 successes=0
while IFS=$'\t' read -r _ tool _; do
  for workload in "${workloads[@]}"; do
    note "${tool}/${workload}"
    if "${HARNESS_DIR}/run.sh" "${mode}" --duration "${duration}" "${tool}" "${workload}"; then successes=$((successes + 1)); else failures=$((failures + 1)); fi
  done
done < <(list_tools)
printf 'linux-tools summary: %d succeeded, %d failed\n' "${successes}" "${failures}" >&2
((failures == 0)) || exit 1
