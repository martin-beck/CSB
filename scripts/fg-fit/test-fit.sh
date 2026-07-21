#!/usr/bin/bash
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
mkdir "$tmp/candidates"
printf 'kernel_a 70\nkernel_b 30\n' > "$tmp/reference.stacks"
printf 'kernel_a 100\n' > "$tmp/candidates/a.html.stacks"
printf 'kernel_b 100\n' > "$tmp/candidates/b.html.stacks"

"$root/scripts/fg-fit/fit.sh" "$tmp/reference.stacks" "$tmp/candidates" "$tmp/output" \
    --epsilon 5 --max-rounds 10 > "$tmp/stdout"
grep -q 'target reached' "$tmp/stdout"
grep -q '^a,' "$tmp/output/weights.csv"
grep -q '^b,' "$tmp/output/weights.csv"
test -s "$tmp/output/fitted.stacks"
awk '$1 ~ /^[0-9]+$/ { value = $2 + 0; if (seen && value < previous) exit 1; previous = value; seen = 1 }' \
    "$tmp/output/progress.log"
echo "fitting test passed"
