#!/usr/bin/env bash
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT
set -Eeuo pipefail
[[ $# == 2 ]] || { printf 'usage: %s TRACE TOOL\n' "$0" >&2; exit 2; }
trace="$1" tool="$2"
[[ -s "${trace}" ]] || { printf 'error: empty trace: %s\n' "${trace}" >&2; exit 1; }
grep -Eq '^[0-9]+ +[a-zA-Z0-9_]+\(' "${trace}" || { printf 'error: no decoded syscalls: %s\n' "${trace}" >&2; exit 1; }
grep -Eq '(exit_group|\+\+\+ exited with)' "${trace}" || { printf 'error: truncated trace: %s\n' "${trace}" >&2; exit 1; }
# collect_strace uses strace -xx, so executable path strings are hex escaped.
# A child exec plus decoded syscalls proves the recipe ran without depending on
# strace's string rendering or a distribution-specific executable path.
grep -Eq 'execve(at)?\(' "${trace}" || { printf 'error: no executed command in %s\n' "${trace}" >&2; exit 1; }
printf 'verified %s: %s\n' "${tool}" "${trace}"
