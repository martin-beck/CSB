#!/bin/bash
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT
set -euo pipefail

cd "$(dirname "$0")"
./refresh.sh
for mode in execl execle execlp execv execvp execvpe execve; do
	test "$(rg -c 'execve\(' "strace-${mode}.log")" -ge 2
done
for mode in fexecve execveat execveat_empty; do
	test "$(rg -c 'execve(at)?\(' "strace-${mode}.log")" -ge 2
done
test "$(rg -c 'execve(at)?\(' strace-all.log)" -ge 11

# Concurrent recorders must all finish and reap their own children.
binary=$(mktemp /tmp/csb-exec-fixture-test.XXXXXX)
trap 'rm -f "$binary" /tmp/csb-exec-fixture-*.out' EXIT
cc -O2 -Wall -Wextra -Werror -o "$binary" exec_fixture.c
pids=()
for i in 1 2 3 4; do
	timeout 20 "$binary" all >"/tmp/csb-exec-fixture-${i}.out" 2>&1 &
	pids+=("$!")
done
for pid in "${pids[@]}"; do
	wait "$pid"
done
