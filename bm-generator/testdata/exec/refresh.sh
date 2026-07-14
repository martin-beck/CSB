#!/bin/bash
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT
set -euo pipefail

cd "$(dirname "$0")"
binary=$(mktemp /tmp/csb-exec-fixture.XXXXXX)
trap 'rm -f "$binary"' EXIT
cc -O2 -Wall -Wextra -Werror -o "$binary" exec_fixture.c
for mode in execl execle execlp execv execvp execvpe fexecve execve execveat execveat_empty all; do
	env -i PATH=/usr/bin:/bin strace -o "strace-${mode}.log.tmp" -a 1 -s 65500 -v -xx -f -Xraw --raw=wait4 \
		-e trace=clone,clone3,fork,vfork,execve,execveat,wait4,exit,exit_group \
		"$binary" "$mode"
	mv "strace-${mode}.log.tmp" "strace-${mode}.log"
done
