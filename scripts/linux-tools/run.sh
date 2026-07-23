#!/usr/bin/env bash
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT
set -Eeuo pipefail
source "$(cd -- "$(dirname -- "$0")" && pwd)/lib/common.sh"
usage() {
  printf 'usage: %s [--trace|--no-trace|--plan] [--duration SECONDS] TOOL [micro|small]\n       %s --list\n' "$0" "$0"
}
[[ "${1:-}" != --list ]] || { list_tools; exit; }
mode=--trace; duration="${DURATION:-10}"
while [[ "${1:-}" == --* ]]; do
  case "$1" in
    --trace|--no-trace|--plan) mode="$1"; shift ;;
    --duration) [[ $# -ge 2 ]] || { usage; exit 2; }; duration="$2"; shift 2 ;;
    *) usage; exit 2 ;;
  esac
done
[[ $# -ge 1 && $# -le 2 ]] || { usage; exit 2; }
tool="$1"; workload="${2:-micro}"
tool_row "${tool}" >/dev/null || die "unknown tool: ${tool}"
[[ "${workload}" =~ ^(micro|small)$ ]] || die "unknown workload: ${workload}"
[[ "${duration}" =~ ^[1-9][0-9]*$ ]] || die 'duration must be a positive integer'
prepare_case "${tool}/${workload}"
if [[ "${mode}" == --plan ]]; then
  printf '%q %q %q %q %q %q\n' "${HARNESS_DIR}/lib/workload.sh" "${tool}" "${PREFIX}/.../${tool}" "${CASE_DIR}" "${workload}" "${duration}"
  exit
fi
install_tool "${tool}"
tool_executable="$(prefix_command "${tool}")" || die "${tool} is not installed below ${PREFIX}"
command=("${HARNESS_DIR}/lib/workload.sh" "${tool}" "${tool_executable}" "${CASE_DIR}" "${workload}" "${duration}")
output="${TRACE_DIR}/$(host_arch)/${tool}/${workload}.strace"
mkdir -p "$(dirname -- "${output}")"
timeout_seconds=7
[[ "${workload}" == small ]] && timeout_seconds=$((duration + 15))
if [[ "${mode}" == --trace ]]; then
  install_tool strace
  prefix_command strace >/dev/null || die "strace is not installed below ${PREFIX}"
  [[ ! -e "${output}" && ! -e "${output}.meta" ]] || die "trace exists: ${output}"
  "${COLLECT_STRACE}" "${output}" timeout --signal=TERM --kill-after=1 "${timeout_seconds}" "${command[@]}"
  "${HARNESS_DIR}/verify.sh" "${output}" "${tool}"
else
  timeout --signal=TERM --kill-after=1 "${timeout_seconds}" "${command[@]}"
fi
