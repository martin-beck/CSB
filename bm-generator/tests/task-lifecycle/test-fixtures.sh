#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BUILD=${TMPDIR:-/tmp}/csb-task-lifecycle-fixtures

"$ROOT/record-traces.sh"

# Parallel repetition verifies that every fixture owns and completes its children.
for name in pthread_create fork vfork clone clone3 combined; do
	timeout 20 sh -c '
		bin=$1
		i=0
		while [ "$i" -lt 16 ]; do
			"$bin" &
			i=$((i + 1))
		done
		wait
	' sh "$BUILD/$name"
done

echo "Task-lifecycle fixtures completed without hangs"
