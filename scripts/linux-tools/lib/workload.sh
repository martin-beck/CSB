#!/usr/bin/env bash
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT
# Dispatch a one-shot micro workload or a broader, timed small workload.
set -Eeuo pipefail
[[ $# == 5 ]] || { printf 'usage: %s TOOL EXECUTABLE CASE_DIR micro|small DURATION\n' "$0" >&2; exit 2; }
tool="$1"; executable="$2"; case_dir="$3"; workload="$4"; duration="$5"
operation="$(cd -- "$(dirname -- "$0")" && pwd)/operation.sh"
lib_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
manifest="${lib_dir}/../tools.tsv"
[[ "${workload}" =~ ^(micro|small)$ ]] || { printf 'unknown workload: %s\n' "${workload}" >&2; exit 2; }
[[ "${duration}" =~ ^[1-9][0-9]*$ ]] || { printf 'duration must be a positive integer\n' >&2; exit 2; }

if [[ "${workload}" == micro ]]; then
  exec "${operation}" "${tool}" "${executable}" "${case_dir}"
fi

rank="$(awk -F '\t' -v tool="${tool}" '$1 !~ /^#/ && $2 == tool {print $1; exit}' "${manifest}")"
[[ "${rank}" =~ ^[0-9]+$ ]] || { printf 'tool missing from manifest: %s\n' "${tool}" >&2; exit 2; }
if ((rank <= 34)); then small_script="${lib_dir}/small-1.sh"
elif ((rank <= 67)); then small_script="${lib_dir}/small-2.sh"
else small_script="${lib_dir}/small-3.sh"
fi
[[ -x "${small_script}" ]] || { printf 'small workload implementation missing: %s\n' "${small_script}" >&2; exit 1; }
exec "${small_script}" "${tool}" "${executable}" "${case_dir}" "${duration}"
