#!/usr/bin/env bash
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT
set -Eeuo pipefail
here="$(cd -- "$(dirname -- "$0")" && pwd)"
count="$(${here}/run.sh --list | wc -l)"
[[ "$count" == 100 ]] || { printf 'expected 100 tools, found %s\n' "$count" >&2; exit 1; }
awk -F '\t' '$1 !~ /^#/ { n++; if ($1 != n || NF != 8) exit 1 } END { exit n != 100 }' "${here}/tools.tsv"
plan="$(mktemp "${TMPDIR:-/tmp}/csb-linux-tools-plan.XXXXXX")"
trap 'rm -f -- "$plan"' EXIT
"${here}/sweep.sh" --plan --run micro >"$plan"
[[ "$(wc -l <"$plan")" == 100 ]]
test_root="$(mktemp -d "${TMPDIR:-/tmp}/csb-linux-tools-test.XXXXXX")"
trap 'rm -f -- "$plan"; rm -rf -- "$test_root"' EXIT
# Do not download packages in the structural test. A shell-only fake prefix
# command proves that run.sh resolves its target from PREFIX and never falls
# back to a host grep executable.
mkdir -p "${test_root}/prefix/bin"
printf '%s\n' '#!/usr/bin/env bash' \
  '[[ ${1:-} == --version ]] && exit 0' \
  'input=${!#}; n=0; found=1' \
  'while IFS= read -r line; do n=$((n+1)); case "$line" in alpha|gamma) printf "%d:%s\\n" "$n" "$line"; found=0;; esac; done <"$input"' \
  'exit "$found"' \
  >"${test_root}/prefix/bin/grep"
chmod +x "${test_root}/prefix/bin/grep"
PREFIX="${test_root}/prefix" "${here}/validate.sh" grep
WORK_DIR="${test_root}/work" PREFIX="${test_root}/prefix" "${here}/run.sh" --no-trace grep
printf 'linux-tools harness tests passed\n'
