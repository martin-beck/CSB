#!/usr/bin/env bash
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT
# Launch one installed tool with a harmless, tool-appropriate probe.
set -Eeuo pipefail
source "$(cd -- "$(dirname -- "$0")" && pwd)/lib/common.sh"

usage() { printf 'usage: %s TOOL|--all\n' "$0"; }
[[ $# == 1 ]] || { usage; exit 2; }

validate_tool() {
  local tool="$1" executable resolved log rc=0
  local -a args=(--version)
  tool_row "${tool}" >/dev/null || die "unknown tool: ${tool}"
  executable="$(prefix_command "${tool}")" || die "${tool} is not installed below ${PREFIX}"
  resolved="$(realpath -e -- "${executable}")" || die "cannot resolve ${executable}"
  [[ "${resolved}" == "$(realpath -m -- "${PREFIX}")/"* ]] || die "${tool} resolves outside PREFIX: ${resolved}"

  case "${tool}" in
    ip) args=(-Version) ;;
    ping) args=(-V) ;;
    ssh) args=(-V) ;;
    scp) args=(-h); rc=1 ;;
    dig) args=(-v) ;;
    nslookup) args=(-version) ;;
    which) args=(ls) ;;
    unzip) args=(-v) ;;
    nc) args=(-h) ;;
    openssl) args=(version) ;;
    java) args=(-version) ;;
    go) args=(version) ;;
    kubectl) args=(version --client=true) ;;
    helm) args=(version --short) ;;
    tmux) args=(-V) ;;
    screen) args=(--version) ;;
    top)
      if "${executable}" -V >/dev/null 2>&1; then args=(-V); else args=(-v); fi
      ;;
    lsof) args=(-v) ;;
    perf) args=(version) ;;
  esac

  mkdir -p "${PREFIX}/validation"
  log="${PREFIX}/validation/${tool}.log"
  set +e
  timeout --signal=TERM --kill-after=1 10 "${executable}" "${args[@]}" >"${log}" 2>&1
  actual_rc=$?
  set -e
  [[ ${actual_rc} -eq ${rc} ]] || die "${tool} validation exited ${actual_rc}, expected ${rc}; see ${log}"
  if grep -Eqi '(error while loading shared libraries|cannot open shared object file|exec format error|permission denied)' "${log}"; then
    die "${tool} validation found a loader or execution error; see ${log}"
  fi
  note "validated ${tool}: ${resolved}"
}

if [[ "$1" == --all ]]; then
  failures=0
  while IFS=$'\t' read -r _ tool _; do
    "${BASH_SOURCE[0]}" "${tool}" || failures=$((failures + 1))
  done < <(list_tools)
  ((failures == 0)) || die "${failures} tools failed validation"
else
  validate_tool "$1"
fi
