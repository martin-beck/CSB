#!/usr/bin/env bash
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT
# Representative, bounded workloads for tools ranked 1--34.
set -Eeuo pipefail

[[ $# == 4 ]] || { printf 'usage: %s TOOL EXECUTABLE CASE_DIR DURATION\n' "$0" >&2; exit 2; }
tool=$1 executable=$2 case_dir=$3 duration=$4
[[ -d "$case_dir" && "$case_dir" != / && "$case_dir" != "$HOME" ]] || { printf 'unsafe case directory\n' >&2; exit 1; }
[[ $duration =~ ^[1-9][0-9]*$ ]] || { printf 'duration must be a positive integer\n' >&2; exit 2; }
cd -- "$case_dir"

# Build all fixtures inside the disposable case directory.  Helper commands are
# resolved through the harness prefix-first PATH.
mkdir -p corpus/a corpus/b work
for ((i=0; i<4000; i++)); do
  printf 'record:%05d user=%s status=%s value=%d lorem ipsum dolor sit amet\n' \
    "$i" "$((i % 37))" "$((i % 5))" "$((i * 17 % 10007))"
done >corpus/records.txt
for ((i=0; i<80; i++)); do printf 'file %d payload %s\n' "$i" "$((i * i))" >"corpus/a/item-$i.txt"; done
printf 'name:score:group\nalice:81:red\nbob:95:blue\ncarol:81:red\ndave:72:blue\n' >corpus/table.txt
printf '#!/bin/sh\nprintf fixture\n' >corpus/script.sh

started=$SECONDS
keep_running() { (( SECONDS - started < duration )); }
run() { command "$executable" "$@"; }
n=0

case "$tool" in
  bash)
    while keep_running; do
      run --noprofile --norc -c 'set -eu; f=$1; out=$2; while IFS=: read -r kind id rest; do case $kind in record) printf "%s:%s\n" "$id" "$rest";; esac; done <"$f" >"$out"; for x in "$out" "$f"; do test -s "$x"; done' _ corpus/records.txt "work/bash-$((n%4)).txt"
      ((n+=1))
    done ;;
  ls)
    while keep_running; do run -la --time-style=long-iso corpus >/dev/null; run -lR corpus >/dev/null; run -liS corpus/a >/dev/null; ((n+=1)); done ;;
  cp)
    while keep_running; do dest="work/copy-$((n%3))"; run -a --reflink=auto corpus "$dest"; run -u corpus/records.txt "$dest/records.txt"; run -R --preserve=mode,timestamps corpus/a "$dest/a2"; ((n+=1)); done ;;
  mv)
    printf 'moving data\n' >work/a
    while keep_running; do run -f work/a work/b; run -f work/b work/c; run -f work/c work/a; ((n+=1)); done ;;
  rm)
    while keep_running; do d="work/remove-$((n%4))"; mkdir -p "$d/sub"; printf x >"$d/a"; printf y >"$d/sub/b"; run -f "$d/a"; run -r "$d"; ((n+=1)); done ;;
  mkdir)
    while keep_running; do run -p -m 0750 "work/tree-$n/a/b/c"; run -p "work/tree-$n/d"; ((n+=1)); if ((n%50==0)); then n=0; fi; done ;;
  cat)
    while keep_running; do run -n corpus/table.txt corpus/records.txt >"work/cat-$((n%3)).txt"; run corpus/a/item-{1,2,3,4}.txt >/dev/null; ((n+=1)); done ;;
  grep)
    while keep_running; do run -nE 'user=(7|17|27) status=[0-2]' corpus/records.txt >"work/matches-$((n%3))" || true; run -rIlE 'payload (1|4|9)' corpus/a >/dev/null; run -cF 'lorem ipsum' corpus/records.txt >/dev/null; ((n+=1)); done ;;
  sed)
    while keep_running; do run -E -e '/status=0/d' -e 's/user=([0-9]+)/account=\1/' -e 's/value=([0-9]+)/metric=\1/' corpus/records.txt >"work/normalized-$((n%3))"; run -n '1~17p' corpus/records.txt >/dev/null; ((n+=1)); done ;;
  awk)
    while keep_running; do run -F'[: =]' '{count[$4]++; sum[$4]+=$8} END {for(k in count) printf "%s %d %.2f\n",k,count[k],sum[k]/count[k]}' corpus/records.txt >"work/report-$((n%3))"; run -F: 'NR>1 {g[$3]+=$2} END {for(k in g) print k,g[k]}' corpus/table.txt >/dev/null; ((n+=1)); done ;;
  find)
    while keep_running; do run corpus -type f -name '*.txt' -size +10c -printf '%P %s %m\n' >"work/find-$((n%3))"; run corpus -type f \( -name 'item-1*.txt' -o -name 'item-2*.txt' \) -exec "$executable" '{}' -prune \; >/dev/null; ((n+=1)); done ;;
  xargs)
    while keep_running; do printf '%s\n' corpus/a/item-{1..40}.txt | run -n 8 -P 2 bash --noprofile --norc -c 'for f; do test -s "$f" || exit; done' _; printf 'one\ntwo words\nthree\n' | run -d '\n' -I{} printf '<%s>\n' '{}' >/dev/null; ((n+=1)); done ;;
  pwd)
    while keep_running; do (cd corpus/a && run -P >/dev/null); (cd work && run -L >/dev/null); run >/dev/null; ((n+=1)); done ;;
  touch)
    while keep_running; do run -a -m "work/event-$((n%100))"; run -d '2020-01-02 03:04:05 UTC' "work/fixed-$((n%100))"; run -r corpus/records.txt "work/ref-$((n%100))"; ((n+=1)); done ;;
  chmod)
    for ((i=0;i<100;i++)); do printf x >"work/mode-$i"; done
    while keep_running; do run 0640 work/mode-*; run u+x,g-w work/mode-*; run -R a+rX work; ((n+=1)); done ;;
  ln)
    while keep_running; do idx=$((n%100)); run -f corpus/records.txt "work/hard-$idx"; run -sfn ../corpus/records.txt "work/sym-$idx"; run -sfn ../corpus/a "work/dir-$idx"; ((n+=1)); done ;;
  head)
    while keep_running; do run -n 100 corpus/records.txt >"work/head-$((n%3))"; run -c 4096 corpus/records.txt >/dev/null; run -n -25 corpus/records.txt >/dev/null; ((n+=1)); done ;;
  tail)
    while keep_running; do run -n 100 corpus/records.txt >"work/tail-$((n%3))"; run -c 4096 corpus/records.txt >/dev/null; run -n +3900 corpus/records.txt >/dev/null; ((n+=1)); done ;;
  sort)
    while keep_running; do run -t= -k3,3n -k2,2 -s corpus/records.txt >"work/sorted-$((n%3))"; run -u -f corpus/records.txt >/dev/null; run -R corpus/records.txt >/dev/null; ((n+=1)); done ;;
  uniq)
    while keep_running; do run -c -f 1 corpus/records.txt >"work/uniq-$((n%3))"; run -d corpus/records.txt >/dev/null; run -u corpus/table.txt >/dev/null; ((n+=1)); done ;;
  cut)
    while keep_running; do run -d: -f2,4 corpus/table.txt >"work/cut-$((n%3))"; run -d' ' -f2-4 corpus/records.txt >/dev/null; run -c1-32 corpus/records.txt >/dev/null; ((n+=1)); done ;;
  tr)
    while keep_running; do run '[:lower:]' '[:upper:]' <corpus/records.txt >"work/upper-$((n%3))"; run -s ' ' <corpus/records.txt >/dev/null; run -cd '[:alnum:]\n' <corpus/records.txt >/dev/null; ((n+=1)); done ;;
  wc)
    while keep_running; do run -lwmc corpus/records.txt corpus/table.txt >"work/count-$((n%3))"; run --max-line-length corpus/records.txt >/dev/null; run -L corpus/a/*.txt >/dev/null; ((n+=1)); done ;;
  tee)
    while keep_running; do run "work/tee-$((n%3))-a" "work/tee-$((n%3))-b" <corpus/records.txt >/dev/null; run -a "work/combined-$((n%3))" <corpus/table.txt >/dev/null; ((n+=1)); done ;;
  date)
    while keep_running; do run -u '+%FT%T.%N%z' >"work/date-$((n%3))"; run -d 'next monday + 2 hours' '+%s %A' >/dev/null; run -r corpus/records.txt --iso-8601=ns >/dev/null; ((n+=1)); done ;;
  env)
    while keep_running; do run -i PATH="$PATH" LANG=C CSB_JOB="$n" bash --noprofile --norc -c 'printf "%s %s\n" "$CSB_JOB" "$LANG"' >"work/env-$((n%3))"; run -u HOME CSB_MODE=test bash --noprofile --norc -c 'test -z "${HOME-}"; test "$CSB_MODE" = test'; ((n+=1)); done ;;
  stat)
    while keep_running; do run --printf='%n %s %b %a %U:%G %y\n' corpus/records.txt corpus/a/*.txt >"work/stat-$((n%3))"; run -f --printf='%T %s %a\n' . >/dev/null; run -L corpus/script.sh >/dev/null; ((n+=1)); done ;;
  file)
    while keep_running; do run --brief --mime-type corpus/* corpus/a/* >"work/file-$((n%3))"; run -k corpus/records.txt corpus/script.sh >/dev/null; run -z corpus/records.txt >/dev/null; ((n+=1)); done ;;
  which)
    while keep_running; do PATH="$(dirname "$executable"):$PATH" run -a bash sh ls grep sed awk >/dev/null || true; run "$tool" >/dev/null || true; ((n+=1)); done ;;
  whereis)
    while keep_running; do run -b bash sh ls grep sed awk >"work/whereis-$((n%3))"; run -s -m bash >/dev/null || true; run -B "$(dirname "$executable")" -f "$tool" >/dev/null; ((n+=1)); done ;;
  tar)
    while keep_running; do a="work/archive-$((n%3)).tar"; run -cf "$a" corpus; run -tf "$a" >/dev/null; mkdir -p "work/extract-$((n%3))"; run -xf "$a" -C "work/extract-$((n%3))"; run -uf "$a" corpus/table.txt; ((n+=1)); done ;;
  gzip)
    while keep_running; do out="work/data-$((n%3)).gz"; run -6 -c corpus/records.txt >"$out"; run -t "$out"; run -dc "$out" >"work/plain-$((n%3))"; run -9 -c corpus/table.txt >/dev/null; ((n+=1)); done ;;
  bzip2)
    while keep_running; do out="work/data-$((n%3)).bz2"; run -6 -c corpus/records.txt >"$out"; run -t "$out"; run -dc "$out" >"work/plain-$((n%3))"; run -9 -c corpus/table.txt >/dev/null; ((n+=1)); done ;;
  xz)
    while keep_running; do out="work/data-$((n%3)).xz"; run -T1 -6 -c corpus/records.txt >"$out"; run -t "$out"; run -dc "$out" >"work/plain-$((n%3))"; run --check=crc32 -T1 -3 -c corpus/table.txt >/dev/null; ((n+=1)); done ;;
  *) printf 'small workload shard 1 does not support %s\n' "$tool" >&2; exit 1 ;;
esac
