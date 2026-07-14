#!/bin/bash
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT
set -euo pipefail

ROOT=$(readlink -f "$(dirname "$0")/../../..")
SYZ="$ROOT/deps/syzkaller"
WORK=${WORK:-$(mktemp -d /tmp/csb-exec-pipeline.XXXXXX)}
TARGET_DIR="$ROOT/bench/targets/exec-pipeline"
BUILD="$WORK/build"

cleanup() { rm -rf "$TARGET_DIR"; }
trap cleanup EXIT
rm -rf "$TARGET_DIR"
mkdir -p "$TARGET_DIR/syz" "$WORK/runs"

for tool in syz-trace2syz syz-extraction syz-prog2c; do
	test -x "$SYZ/bin/$tool" || { echo "missing $SYZ/bin/$tool" >&2; exit 1; }
done

declare -A individual combined
traces=(execl execle execlp execv execvp execvpe fexecve execve execveat execveat_empty all)
for name in "${traces[@]}"; do
	base="$WORK/$name"
	mkdir -p "$base/progs" "$base/extracted"
	(
		cd "$ROOT/bm-generator"
		DIR_PROG="$base/progs" DIR_SYZ_SRC="$SYZ" ./02_parse.sh "testdata/exec/strace-$name.log"
		DIR_PROG="$base/progs" DIR_OUT="$base/extracted" DIR_SYZ_SRC="$SYZ" \
			MINCALLS=1 JOBS=1 ./03_extract.sh
	) >"$base/generator.log" 2>&1

	found=0
	while IFS= read -r prog; do
		kind=$(rg -o 'syz_csb_(execveat|fexecve|execve)' "$prog" | head -1 | sed 's/syz_csb_//')
		found=1
		if [[ $name == all ]]; then combined[$kind]=$prog
		elif [[ -z ${individual[$kind]:-} ]]; then individual[$kind]=$prog
		fi
	done < <(rg -l 'syz_csb_(execveat|fexecve|execve)' "$base/extracted" | sort)
	test "$found" -eq 1 || { echo "$name produced no exec lifecycle" >&2; exit 1; }
done

combined_prog=$(find "$WORK/all/progs" -maxdepth 1 -name '*.prog' | head -1)
test "$(rg -c 'syz_csb_execve\(' "$combined_prog")" -eq 7
test "$(rg -c 'syz_csb_execveat\(' "$combined_prog")" -eq 1
test "$(rg -c 'syz_csb_fexecve\(' "$combined_prog")" -eq 2

targets=()
for source in individual combined; do
	for kind in execve execveat fexecve; do
		eval 'prog=${'"$source"'[$kind]:-}'
		test -n "$prog" || { echo "$source trace lacks $kind" >&2; exit 1; }
		target="exec_${source}_${kind}"
		out="$WORK/$target"
		mkdir -p "$out"
		if rg -q '^[^\n]*(exit|exit_group)\(' "$prog"; then
			echo "unsafe termination follows lifecycle in $prog" >&2
			exit 1
		fi
		"$SYZ/bin/syz-prog2c" -csb -trace=true -format=false -prog "$prog" -cfile "$out/generated.h" \
			>"$out/prog2c.log" 2>&1
		generated=$(find "$out" -name 'generated*.h' | head -1)
		cp "$generated" "$TARGET_DIR/syz/$target.h"
		sed -e "s/@SYZ_HEADER@/$target.h/g" -e "s/@TARGET@/$target/g" \
			"$ROOT/bm-generator/testdata/exec/csb-target.h.in" >"$TARGET_DIR/$target.h"
		targets+=("exec-pipeline_$target")
	done
done

cmake -S "$ROOT" -B "$BUILD" -DCMAKE_BUILD_TYPE=Release >"$WORK/cmake.log"
cmake --build "$BUILD" -j"$(nproc)" --target "${targets[@]}" >>"$WORK/cmake.log"

for target in "${targets[@]}"; do
	bin="$BUILD/bench/$target"
	kind=${target##*_}
	for threads in 1 4; do
		prefix="$WORK/runs/$target-t$threads"
		before=$(ps -eo pid=,stat=,comm= | awk '$2 ~ /^Z/ && $3 ~ /^exec-pipeline_/ {print $1}' | sort)
		timeout 30 strace -qq -f -s 128 -e trace=clone,clone3,fork,vfork,execve,execveat,wait4 \
			-o "$prefix.strace" "$bin" -t="$threads" -n=0 -d=1 -s=0 -op0=1024 \
			>"$prefix.stdout" 2>"$prefix.stderr"
		rg -q 'wait4\(' "$prefix.strace"
		case "$kind" in
			execve) rg -q 'execve\("/bin/true"' "$prefix.strace" ;;
			execveat) rg -q 'execveat\(AT_FDCWD, "/bin/true"' "$prefix.strace" ;;
			fexecve) rg -q 'execveat\([^,]+, ""' "$prefix.strace" ;;
		esac
		! pgrep -f "^$bin( |$)" >/dev/null
		after=$(ps -eo pid=,stat=,comm= | awk '$2 ~ /^Z/ && $3 ~ /^exec-pipeline_/ {print $1}' | sort)
		test "$after" = "$before" || { echo "new benchmark zombie after $target" >&2; exit 1; }
		echo "$target t=$threads: OK"
	done
done

# One native campaign proves integration with bm-runner; setup failures are evidence, not hidden.
runner_cfg="$WORK/runner.json"
runner_target=${targets[0]}
printf '{"plots":[],"benchmark_config":{"noise":[0],"threads":{"values":[[1,4]]},"duration":1,"repeat":1,"exec_env":{"native":[]}},"containers":{"core_count":4,"container_list":{"values":[[1]]}},"applications":[{"name":"%s","path":"%s","operations":[1024]}]}\n' \
	"$runner_target" "$BUILD/bench" >"$runner_cfg"
if [[ ${RUN_BM_RUNNER:-1} == 1 ]]; then
	python=${CSB_PYTHON:-$ROOT/venv/bin/python3}
	if [[ ! -x "$python" ]]; then
		echo "bm-runner native campaign blocked: $python is not configured" >&2
	else
		set +e
		(cd "$ROOT/bm-runner" && CSB_NO_BUILD_BENCH=ON timeout 180 "$python" \
			main.py --title exec-lifecycle-e2e --config "$runner_cfg") >"$WORK/bm-runner.log" 2>&1
		runner_status=$?
		set -e
		if [[ $runner_status -eq 0 ]]; then
			echo "bm-runner native campaign: OK"
		else
			echo "bm-runner native campaign blocked (status $runner_status):" >&2
			tail -30 "$WORK/bm-runner.log" >&2
		fi
	fi
fi

echo "Pipeline evidence: $WORK"
