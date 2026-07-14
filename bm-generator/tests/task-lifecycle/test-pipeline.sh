#!/bin/bash
set -euo pipefail

ROOT=$(readlink -f "$(dirname "$0")/../../..")
SYZ="$ROOT/deps/syzkaller"
WORK=${WORK:-$(mktemp -d /tmp/csb-task-lifecycle-pipeline.XXXXXX)}
TARGET_DIR="$ROOT/bench/targets/task-lifecycle-pipeline"
BUILD="$WORK/build"

cleanup() { rm -rf "$TARGET_DIR"; }
trap cleanup EXIT
rm -rf "$TARGET_DIR"
mkdir -p "$TARGET_DIR/syz" "$WORK/direct"

export PATH=/usr/local/go/bin:$PATH
export GOCACHE=${GOCACHE:-$WORK/go-cache}
make -C "$SYZ" trace2syz extraction prog2c >/dev/null

targets=()
for name in pthread_create fork vfork clone clone3 combined; do
    base="$WORK/$name"
    mkdir -p "$base/deserialized" "$base/extracted" "$base/headers"
    (
        cd "$ROOT/bm-generator"
        DIR_PROG="$base/deserialized" DIR_SYZ_SRC="$SYZ" \
            ./02_parse.sh "tests/task-lifecycle/traces/$name.strace"
        DIR_PROG="$base/deserialized" DIR_OUT="$base/extracted" \
            DIR_SYZ_SRC="$SYZ" MINCALLS=1 JOBS=1 ./03_extract.sh
    ) >"$base/generator.log" 2>&1

    while IFS= read -r prog; do
        kind=$(rg -o 'syz_csb_(thread_create_join|fork_wait|vfork_wait)' \
            "$prog" | head -1 | sed 's/syz_csb_//')
        target="tl_${name}_${kind}"
        [[ -e "$TARGET_DIR/$target.h" ]] && continue
        "$SYZ/bin/syz-prog2c" -csb -trace=true -format=false \
            -prog "$prog" -cfile "$base/headers/$target.h" \
            >>"$base/generator.log" 2>&1
        generated=$(find "$base/headers" -maxdepth 1 -name "$target*.h" | head -1)
        cp "$generated" "$TARGET_DIR/syz/$target.h"
        sed -e "s/@SYZ_HEADER@/$target.h/g" -e "s/@TARGET@/$target/g" \
            "$ROOT/bm-generator/tests/task-lifecycle/csb-target.h.in" \
            >"$TARGET_DIR/$target.h"
        targets+=("task-lifecycle-pipeline_$target")
        printf '%s -> %s\n' "$name" "$kind"
    done < <(find "$base/extracted" -type f -name '*syz_csb_*.prog' | sort)
done

[[ ${#targets[@]} -eq 8 ]] || {
    echo "expected 8 generated lifecycle targets, got ${#targets[@]}" >&2
    exit 1
}

cmake -S "$ROOT" -B "$BUILD" -DCMAKE_BUILD_TYPE=Release >/dev/null
cmake --build "$BUILD" -j"$(nproc)" --target "${targets[@]}" >/dev/null

for target in "${targets[@]}"; do
    bin="$BUILD/bench/$target"
    for threads in 1 4; do
        prefix="$WORK/direct/$target-t$threads"
        timeout 20 strace -f -c -o "$prefix.strace-count" \
            "$bin" -t="$threads" -n=0 -d=1 -s=0 -op0=1024 \
            >"$prefix.stdout" 2>"$prefix.stderr"
        test -s "$prefix.stdout"
        ! pgrep -f "^$bin( |$)" >/dev/null

        case "$target" in
            *thread_create_join) rg -q ' (clone|clone3)$' "$prefix.strace-count" ;;
            *vfork_wait) rg -q ' vfork$' "$prefix.strace-count"; rg -q ' wait4$' "$prefix.strace-count" ;;
            *fork_wait) rg -q ' (clone|fork)$' "$prefix.strace-count"; rg -q ' wait4$' "$prefix.strace-count" ;;
        esac
        printf '%s t=%d: OK\n' "$target" "$threads"
    done
done

if ps -eo stat=,comm= | awk '$1 ~ /^Z/ && $2 ~ /^task-lifecycle/ {found=1} END {exit found ? 0 : 1}'; then
    echo "a generated benchmark zombie remains" >&2
    exit 1
fi

if [[ ${RUN_BM_RUNNER:-0} == 1 ]]; then
    echo "RUN_BM_RUNNER requires Docker access during CSB configuration; use runner-config.json after exposing the Docker socket." >&2
    exit 77
else
    echo "bm-runner skipped (set RUN_BM_RUNNER=1 to check Docker availability)"
fi
echo "Pipeline evidence: $WORK"
