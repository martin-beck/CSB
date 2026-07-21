#!/usr/bin/bash
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
actual=$(printf 'run1;kernel_a 2\nrun2;kernel_a 3\nrun1;kernel_b 1\n' | \
    "$root/scripts/fg-diff/canonicalize-folded.py")
expected=$(printf 'kernel_a 5\nkernel_b 1')
test "$actual" = "$expected"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
printf 'a,a,0\na,b,2\nb,a,2\nb,b,0\n' > "$tmp/diff.csv"
actual=$(python3 "$root/scripts/fg-diff/diffset.py" --cutoff 5 --input "$tmp/diff.csv")
test "$actual" = "a"
echo "selection test passed"
