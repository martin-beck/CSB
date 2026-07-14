#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BUILD=${TMPDIR:-/tmp}/csb-task-lifecycle-fixtures
TRACES=$ROOT/traces

command -v cc >/dev/null
command -v strace >/dev/null
mkdir -p "$BUILD" "$TRACES"

for name in pthread_create fork vfork clone clone3 combined; do
	cc -std=gnu11 -O2 -Wall -Wextra -Werror -pthread \
		"$ROOT/$name.c" -o "$BUILD/$name"
	strace -o "$TRACES/$name.strace" -a 1 -s 65500 -v -xx -f -Xraw \
		--raw=wait4 -e trace=clone,clone3,fork,vfork,wait4,waitid,exit,exit_group \
		"$BUILD/$name"
done

grep -Eq 'clone3?\(' "$TRACES/pthread_create.strace"
grep -Eq '(fork|clone)\(' "$TRACES/fork.strace"
grep -q 'vfork(' "$TRACES/vfork.strace"
grep -q 'clone(' "$TRACES/clone.strace"
grep -q 'clone3(' "$TRACES/clone3.strace"
grep -q 'vfork(' "$TRACES/combined.strace"
grep -q 'clone3(' "$TRACES/combined.strace"

echo "Recorded task-lifecycle traces in $TRACES"
