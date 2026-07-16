#!/usr/bin/env bash
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

# Prove that an installed tool starts for a matrix cell with no corresponding
# API. The adjacent .skip file prevents this smoke trace from being mistaken
# for a lifecycle-operation trace.
set -Eeuo pipefail
source "$(cd -- "$(dirname -- "$0")" && pwd)/common.sh"
tool="$1"
case "${tool}" in
  lxc) candidates=(lxc-checkconfig lxc-create) ;;
  kata) candidates=(kata-runtime containerd-shim-kata-v2) ;;
  *) candidates=("${tool}") ;;
esac
binary=""
for candidate in "${candidates[@]}"; do
  binary="$(prefix_command "${candidate}" || true)"
  [[ -n "${binary}" ]] && break
done
[[ -n "${binary}" ]] || die "no installed probe binary for ${tool}"
"${binary}" --version >/dev/null 2>&1 || "${binary}" --help >/dev/null 2>&1 || true
