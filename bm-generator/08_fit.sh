#!/bin/bash
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

# Fit the step-07 candidate profiles to a portable reference captured on machine A.
set -euo pipefail
if [ "$#" -lt 1 ]; then
    echo "usage: $0 REFERENCE_STACKS [FIT_OPTIONS ...]" >&2
    exit 2
fi
reference=$(realpath "$1"); shift
root=$(cd "$(dirname "$0")/.." && pwd)
"$root/scripts/fg-fit/fit.sh" "$reference" "$root/bench-select" \
    "$root/bench-fit" "$@"
