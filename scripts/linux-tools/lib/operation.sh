#!/usr/bin/env bash
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT
# Mutating examples are confined to CASE_DIR, recreated by run.sh.
set -Eeuo pipefail
[[ $# == 3 ]] || { printf 'usage: %s TOOL EXECUTABLE CASE_DIR\n' "$0" >&2; exit 2; }
tool="$1"; executable="$2"; case_dir="$3"
[[ -d "$case_dir" && "$case_dir" != / && "$case_dir" != "$HOME" ]] || { printf 'unsafe case directory\n' >&2; exit 1; }
cd -- "$case_dir"
printf 'gamma\nalpha\nbeta\nalpha\n' > input.txt
printf 'one:1\ntwo:2\n' > fields.txt
mkdir -p tree/sub; printf 'payload\n' > tree/sub/payload.txt
run() { command "$executable" "$@"; }
case "$tool" in
 bash) run --noprofile --norc -c 'for x in alpha beta gamma; do printf "%s\n" "$x"; done' >output.txt;;
 ls) run -la tree >output.txt;; cp) run -a tree copied;;
 mv) cp input.txt source.txt; run source.txt target.txt;; rm) cp input.txt remove.txt; run -f -- remove.txt;;
 mkdir) run -p created/a/b;; cat) run input.txt fields.txt >output.txt;;
 grep) run -n -E 'alpha|gamma' input.txt >output.txt;; sed) run -E 's/^/line: /' input.txt >output.txt;;
 awk) run -F: '{s += $2} END {print s}' fields.txt >output.txt;; find) run tree -type f -print >output.txt;;
 xargs) printf 'alpha\nbeta\n' | run -n 1 printf 'item=%s\n' >output.txt;; pwd) run -P >output.txt;;
 touch) run -t 202001020304.05 touched.txt;; chmod) cp input.txt mode.txt; run 0640 mode.txt;;
 ln) run input.txt hardlink.txt; run -s input.txt symlink.txt;; head) run -n 2 input.txt >output.txt;;
 tail) run -n 2 input.txt >output.txt;; sort) run input.txt >output.txt;; uniq) sort input.txt | run -c >output.txt;;
 cut) run -d: -f1 fields.txt >output.txt;; tr) run '[:lower:]' '[:upper:]' <input.txt >output.txt;;
 wc) run -l -w -c input.txt >output.txt;; tee) printf 'captured\n' | run output.txt >/dev/null;;
 date) run -u '+%Y-%m-%dT%H:%M:%SZ' >output.txt;; env) run CSB_TRACE_EXAMPLE=1 sh -c 'printf "%s\n" "$CSB_TRACE_EXAMPLE"' >output.txt;;
 stat) run --printf='%n %s %a\n' input.txt >output.txt;; file) run input.txt tree >output.txt;;
 which) run sh >output.txt;; whereis) run sh >output.txt;;
 tar) run -cf sample.tar tree; run -tf sample.tar >output.txt;;
 gzip) cp input.txt sample.txt; run -k sample.txt; run -dc sample.txt.gz >output.txt;;
 bzip2) cp input.txt sample.txt; run -k sample.txt; run -dc sample.txt.bz2 >output.txt;;
 xz) cp input.txt sample.txt; run -k sample.txt; run -dc sample.txt.xz >output.txt;;
 zip) run -q -r sample.zip tree; run -sf sample.zip >output.txt;;
 unzip) zip -q -r sample.zip tree; mkdir extracted; run -q sample.zip -d extracted;;
 diff) printf 'alpha\nbeta\n' >a; printf 'alpha\ngamma\n' >b; run -u a b >change.diff || [[ $? == 1 ]];;
 patch) printf 'old\n' >target; printf '%s\n' '--- target' '+++ target' '@@ -1 +1 @@' '-old' '+new' >change.diff; run -s target change.diff;;
 less) run -F -X input.txt >output.txt;; vi) printf 'Goedited\033:wq\n' | run -Nu NONE -n input.txt >/dev/null 2>&1;;
 nano) run --version >output.txt;; ps) run -eo pid,ppid,stat,comm >output.txt;; top) run -b -n 1 -d 0.1 >output.txt;;
 free) run -h >output.txt;; uptime) run >output.txt;; uname) run -a >output.txt;; hostname|id|whoami|groups) run >output.txt;;
 df) run -P "$case_dir" >output.txt;; du) run -a tree >output.txt;; lsblk) run -J -o NAME,TYPE,SIZE >output.txt;;
 lscpu) run -J >output.txt;; mount) run >output.txt;; dmesg) run --level=err,warn --since '1 minute ago' >output.txt 2>&1 || true;;
 journalctl) run --no-pager -n 10 --since '1 minute ago' >output.txt 2>&1 || true;;
 systemctl) run --no-pager --no-legend list-units --type=service --state=running >output.txt 2>&1 || true;;
 ip) run -details -statistics address show >output.txt;; ss) run -H -a -n >output.txt;;
 ping) run -n -c 3 -W 1 127.0.0.1 >output.txt;; traceroute) run -n -m 3 -w 1 127.0.0.1 >output.txt 2>&1;;
 curl) run --fail --silent --show-error "file://${case_dir}/input.txt" -o output.txt;;
 wget) python3 -m http.server 18080 --bind 127.0.0.1 >server.log 2>&1 & p=$!; trap 'kill "$p" 2>/dev/null || true' EXIT; sleep .2; run -q -O output.txt http://127.0.0.1:18080/input.txt; kill "$p"; wait "$p" 2>/dev/null || true; trap - EXIT;;
 ssh) run -F /dev/null -G localhost >output.txt;; scp) run -F /dev/null input.txt "$case_dir/scp-copy.txt";;
 rsync) run -a --checksum tree/ copied/;; dig) run @127.0.0.1 localhost A +time=1 +tries=1 >output.txt 2>&1 || true;;
 nslookup) run -timeout=1 localhost 127.0.0.1 >output.txt 2>&1 || true;; nc) run -z -w 1 127.0.0.1 9 >output.txt 2>&1 || true;;
 openssl) run dgst -sha256 input.txt >digest.txt; run rand -out random.bin 64;;
 git) run init -q repo; run -C repo config user.email trace@example.invalid; run -C repo config user.name Trace; cp input.txt repo/; run -C repo add input.txt; run -C repo commit -q -m initial; run -C repo status --short >output.txt;;
 make) printf 'all:\n\t@printf "built\\n" > output.txt\n' >Makefile; run --no-print-directory;;
 gcc) printf '#include <stdio.h>\nint main(void){puts("hello");}\n' >hello.c; run -O0 hello.c -o hello; ./hello >output.txt;;
 g++) printf '#include <iostream>\nint main(){std::cout << "hello\\n";}\n' >hello.cc; run -O0 hello.cc -o hello; ./hello >output.txt;;
 cmake) printf 'cmake_minimum_required(VERSION 3.10)\nproject(trace C)\nadd_executable(hello hello.c)\n' >CMakeLists.txt; printf 'int main(void){return 0;}\n' >hello.c; run -S . -B build >output.txt;;
 python3) run -c 'from pathlib import Path; Path("python.txt").write_text("\n".join(map(str,range(1000)))); print(sum(range(1000)))' >output.txt;;
 perl) run -e 'open my $f, ">", "perl.txt" or die $!; print $f join("\n",1..1000); print scalar reverse("linux"),"\n"' >output.txt;;
 ruby) run -e 'File.write("ruby.txt",(1..1000).to_a.join("\n")); puts (1..1000).sum' >output.txt;;
 node) run -e 'require("fs").writeFileSync("node.txt",Array.from({length:1000},(_,i)=>i).join("\n")); console.log(499500)' >output.txt;;
 npm) run init --yes --ignore-scripts >output.txt;; java) run -version >output.txt 2>&1;;
 javac) printf 'class Hello { public static void main(String[] a){System.out.println("hello");} }\n' >Hello.java; run Hello.java; java Hello >output.txt;;
 go) printf 'package main\nimport("fmt";"os")\nfunc main(){os.WriteFile("go.txt",[]byte("data"),0600);fmt.Println("hello")}\n' >main.go; GOCACHE="$case_dir/gocache" GOPATH="$case_dir/gopath" run run main.go >output.txt;;
 cargo) mkdir -p src; printf '[package]\nname="trace_example"\nversion="0.1.0"\nedition="2021"\n' >Cargo.toml; printf 'fn main(){println!("hello");}\n' >src/main.rs; CARGO_HOME="$case_dir/cargo-home" CARGO_TARGET_DIR="$case_dir/target" run check --offline --quiet;;
 rustc) printf 'fn main(){println!("hello");}\n' >main.rs; run main.rs -o hello; ./hello >output.txt;;
 docker) run version >output.txt 2>&1 || run info >output.txt 2>&1 || true;; podman) run info --format json >output.txt 2>&1 || true;;
 kubectl) KUBECONFIG="$case_dir/empty-kubeconfig" run config view --raw >output.txt;;
 helm) mkdir -p chart/templates; printf 'apiVersion: v2\nname: trace\nversion: 0.1.0\n' >chart/Chart.yaml; printf 'apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: trace\n' >chart/templates/config.yaml; run template trace chart >output.txt;;
 jq) printf '{"items":[3,1,2]}\n' | run '.items | sort | {count:length,values:.}' >output.txt;;
 yq) printf 'items:\n  - 3\n  - 1\n' >input.yaml; run '.items' input.yaml >output.txt;;
 tmux) s="csb-trace-$$"; run -L "$s" new-session -d 'printf tmux > tmux.txt'; sleep .2; run -L "$s" kill-server 2>/dev/null || true;;
 screen) session="csb-trace-$$"; trap '"$executable" -S "$session" -X quit 2>/dev/null || true' EXIT; run -DmS "$session" sh -c 'printf screen > screen.txt'; sleep .5; run -S "$session" -X quit 2>/dev/null || true; trap - EXIT;;
 strace) run -o nested.strace -f sh -c 'printf traced > nested.txt';;
 lsof) run -a -p "$$" -d cwd,0,1,2 >output.txt;; tcpdump) run -D >output.txt;;
 perf) run stat -o perf.txt -- sh -c 'i=0; while [ "$i" -lt 1000 ]; do i=$((i+1)); done' 2>/dev/null || true;;
 time) run -p -o timing.txt sh -c 'printf timed > timed.txt';;
 watch) run -n .2 -t -x sh -c 'printf watched' >output.txt 2>&1 & p=$!; sleep 1; kill "$p" 2>/dev/null || true; wait "$p" 2>/dev/null || true;;
 *) printf 'no operation recipe for %s\n' "$tool" >&2; exit 1;;
esac
