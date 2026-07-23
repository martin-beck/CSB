#!/usr/bin/env bash
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT
set -Eeuo pipefail
source "$(cd -- "$(dirname -- "$0")" && pwd)/lib/common.sh"
usage() { printf 'usage: %s TOOL|--all|--list\n' "$0"; }
[[ $# == 1 ]] || { usage; exit 2; }
[[ "$1" != --list ]] || { list_tools; exit; }
mkdir -p "${PREFIX}/bin"
if [[ "$1" == --all ]]; then
  failures=0
  while IFS=$'\t' read -r _ tool _; do
    "${BASH_SOURCE[0]}" "${tool}" || failures=$((failures + 1))
  done < <(list_tools)
  ((failures == 0)) || die "${failures} tools could not be set up"
else
  install_tool "$1"
  "${HARNESS_DIR}/validate.sh" "$1"
fi
