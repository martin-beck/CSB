#!/bin/bash
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

set -eu

root=$(cd "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d)
group="release-guards-$$"
trap 'rm -rf "$tmp" "$root/bench/targets/$group"' EXIT

fail() {
  echo "$1" >&2
  exit 1
}

make_tool() {
  path=$1
  body=$2
  mkdir -p "$(dirname "$path")"
  printf '#!/bin/sh\n%s\n' "$body" > "$path"
  chmod +x "$path"
}

# Archived templates must not be picked up automatically: the v2.0.1 header
# template and the current template otherwise race to write the same file.
if grep -Eq 'file\(GLOB[[:space:]]+TEMPLATES' "$root/bm-generator/templates/CMakeLists.txt"; then
  fail "template generation still automatically includes archived templates"
fi

# A failed parallel extraction worker must fail the stage.
mkdir -p "$tmp/extract-in" "$tmp/extract-out" "$tmp/syz/bin"
printf '# csb.trace.os=linux\n# csb.trace.arch=amd64\ngetpid()\n' > "$tmp/extract-in/input.prog"
make_tool "$tmp/syz/bin/syz-extraction" 'exit 23'
if (cd "$root/bm-generator" &&
    DIR_SYZ_SRC="$tmp/syz" DIR_PROG="$tmp/extract-in" DIR_OUT="$tmp/extract-out" JOBS=1 ./03_extract.sh); then
  fail "03_extract.sh masked a worker failure"
fi

# Failure of either generated-template target must fail the stage.
mkdir -p "$tmp/bin"
make_tool "$tmp/bin/cmake" 'case "$*" in *syz_single.h.in*) exit 24;; esac; exit 0'
if (cd "$root/bm-generator" && PATH="$tmp/bin:$PATH" ./07_generate.sh); then
  fail "07_generate.sh masked the first template failure"
fi

# Existing generated headers are stale inputs, not a resumable output set.
mkdir -p "$root/bench/targets/$group/syz" "$tmp/prepare-in"
printf 'stale\n' > "$root/bench/targets/$group/syz/stale.h"
printf '# csb.trace.os=linux\n# csb.trace.arch=amd64\ngetpid()\n' > "$tmp/prepare-in/input.prog"
make_tool "$tmp/syz/bin/syz-prog2c" 'exit 0'
if (cd "$root/bm-generator" && CSB_RESULTS_GROUP="$group" DIR_SYZ_SRC="$tmp/syz" DIR_PROG="$tmp/prepare-in" JOBS=1 ./06_prepare.sh); then
  fail "06_prepare.sh accepted a non-empty generated-header directory"
fi

# Flattening two nested programs with the same basename would race and overwrite.
rm -rf "$root/bench/targets/$group"
mkdir -p "$tmp/collisions/a" "$tmp/collisions/b"
for dir in a b; do
  printf '# csb.trace.os=linux\n# csb.trace.arch=amd64\ngetpid()\n' > "$tmp/collisions/$dir/same.prog"
done
if (cd "$root/bm-generator" && CSB_RESULTS_GROUP="$group" DIR_SYZ_SRC="$tmp/syz" DIR_PROG="$tmp/collisions" JOBS=2 ./06_prepare.sh); then
  fail "06_prepare.sh accepted colliding program basenames"
fi

# A successful tool exit without any header (for example, all inputs skipped)
# is not a successfully prepared benchmark set.
rm -rf "$root/bench/targets/$group"
if (cd "$root/bm-generator" && CSB_RESULTS_GROUP="$group" DIR_SYZ_SRC="$tmp/syz" DIR_PROG="$tmp/prepare-in" JOBS=1 ./06_prepare.sh); then
  fail "06_prepare.sh accepted an empty generated-header set"
fi

# Selection must stop immediately when any benchmark run fails.
fake="$tmp/select-root"
mkdir -p "$fake/results" "$fake/bm-runner" "$fake/scripts/fg-diff" "$fake/scripts/fg-merge" \
  "$fake/deps" "$fake/venv/bin" "$fake/config"
cp "$root/scripts/fg-diff/select-benchmarks.sh" "$fake/scripts/fg-diff/select-benchmarks.sh"
printf '{}\n' > "$fake/config/input.json"
printf ':\n' > "$fake/venv/bin/activate"
make_tool "$fake/scripts/run-single.sh" 'exit 25'
make_tool "$fake/scripts/fg-diff/filter-all.sh" 'exit 0'
make_tool "$fake/scripts/fg-diff/diff-all.sh" 'printf "a,a,0\\n"'
make_tool "$tmp/bin/python3" 'exit 0'
if (cd "$fake" && PATH="$tmp/bin:$PATH" CSB_RESULTS_GROUP=test ./scripts/fg-diff/select-benchmarks.sh ./config/input.json); then
  fail "select-benchmarks.sh masked a benchmark failure"
fi

echo "release guard tests passed"
