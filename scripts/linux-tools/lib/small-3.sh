#!/usr/bin/env bash
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT
# Realistic, bounded "small" workloads for tools 68--100.
set -Eeuo pipefail

[[ $# == 4 ]] || { printf 'usage: %s TOOL EXECUTABLE CASE_DIR DURATION\n' "$0" >&2; exit 2; }
tool=$1 executable=$2 case_dir=$3 duration=$4
[[ $duration =~ ^[1-9][0-9]*$ ]] || { printf 'DURATION must be a positive integer\n' >&2; exit 2; }
[[ -d $case_dir && $case_dir != / && $case_dir != "$HOME" ]] || { printf 'unsafe case directory\n' >&2; exit 1; }
cd -- "$case_dir"
end=$((SECONDS + duration))
run() { command "$executable" "$@"; }
active() { (( SECONDS < end )); }

case "$tool" in
  dig)
    n=0; while active; do
      run +tries=1 +time=1 +noall +answer localhost A localhost AAAA localhost SOA >"dig-$((n%8)).out" 2>&1 || true
      run +tries=1 +time=1 +short -x 127.0.0.1 >>"dig-$((n%8)).out" 2>&1 || true
      ((++n))
    done
    ;;
  nslookup)
    n=0; while active; do
      run -timeout=1 -type=A localhost >"lookup-$((n%8)).out" 2>&1 || true
      run -timeout=1 -type=AAAA localhost >>"lookup-$((n%8)).out" 2>&1 || true
      run -timeout=1 127.0.0.1 >>"lookup-$((n%8)).out" 2>&1 || true
      ((++n))
    done
    ;;
  nc)
    # Each iteration runs an actual loopback request/reply exchange.
    port=$((20000 + ($$ % 20000))); n=0
    while active; do
      (printf 'reply:%s\n' "$n" | run -l 127.0.0.1 "$port" >"server-$n.in") & server=$!
      for ((spin=0; spin<200; ++spin)); do
        active || break
        printf 'request:%s\n' "$n" | run -w 1 127.0.0.1 "$port" >"client-$n.out" 2>/dev/null && break || :
      done
      wait "$server" 2>/dev/null || true; ((++n)); port=$((port == 39999 ? 20000 : port + 1))
    done
    ;;
  openssl)
    run rand -out payload.bin 1048576; run genpkey -algorithm ED25519 -out key.pem >/dev/null 2>&1
    n=0; while active; do
      run dgst -sha256 -sha512 payload.bin >"digest-$((n%8)).txt"
      run pkeyutl -sign -inkey key.pem -rawin -in payload.bin -out signature.bin
      run pkeyutl -verify -pubin -inkey <(run pkey -in key.pem -pubout) -rawin -in payload.bin -sigfile signature.bin >/dev/null
      run enc -aes-256-cbc -pbkdf2 -salt -pass pass:trace -in payload.bin -out encrypted.bin
      run enc -d -aes-256-cbc -pbkdf2 -pass pass:trace -in encrypted.bin -out decrypted.bin
      ((++n))
    done
    ;;
  git)
    run init -q repo; run -C repo config user.name Trace; run -C repo config user.email trace@example.invalid
    n=0; while active; do
      printf 'record %s %s\n' "$n" "$RANDOM" >>repo/data; run -C repo add data; run -C repo commit -q -m "record $n"
      run -C repo branch -f work HEAD; run -C repo status --porcelain=v2 >status
      run -C repo log --oneline --decorate -20 >log
      (( n == 0 )) || run -C repo diff HEAD~1 HEAD >last.patch
      (( n % 8 )) || { run -C repo pack-refs --all; run -C repo gc --auto; }
      ((++n))
    done
    ;;
  make)
    mkdir src
    printf '#include "value.h"\n#include <stdio.h>\nint main(void){printf("%%d\\n", VALUE);}\n' >src/main.c
    printf 'CC ?= cc\nCFLAGS=-O2 -Wall\napp: main.o\n\t$(CC) $(CFLAGS) $< -o $@\nmain.o: src/main.c src/value.h\n\t$(CC) $(CFLAGS) -c $< -o $@\nclean:\n\trm -f app main.o\n' >Makefile
    n=0; while active; do printf '#define VALUE %s\n' "$n" >src/value.h; run --no-print-directory -j2 app; ./app >>runs; ((++n)); done
    ;;
  gcc|g++)
    if [[ $tool == gcc ]]; then ext=c; printf '#include <stdio.h>\n#ifndef N\n#define N 1\n#endif\nint main(void){long s=0;for(int i=0;i<100000;i++)s+=(i^N);printf("%%ld\\n",s);}\n' >work.c
    else ext=cc; printf '#include <algorithm>\n#include <iostream>\n#include <numeric>\n#include <vector>\n#ifndef N\n#define N 1\n#endif\nint main(){std::vector<int> v(10000);std::iota(v.begin(),v.end(),N);std::sort(v.rbegin(),v.rend());std::cout<<std::accumulate(v.begin(),v.end(),0LL)<<"\\n";}\n' >work.cc; fi
    n=0; while active; do run -O2 -g -Wall -Wextra -DN="$n" "work.$ext" -o app; ./app >"run-$((n%8)).out"; ((++n)); done
    ;;
  cmake)
    mkdir src; printf 'cmake_minimum_required(VERSION 3.10)\nproject(small C)\nenable_testing()\nadd_library(calc src/calc.c)\nadd_executable(app src/main.c)\ntarget_link_libraries(app calc)\nadd_test(NAME app COMMAND app)\n' >CMakeLists.txt
    printf 'int calc(int x){return x*x;}\n' >src/calc.c; printf 'int calc(int);int main(void){return calc(3)!=9;}\n' >src/main.c
    n=0; while active; do run -S . -B build -DCMAKE_BUILD_TYPE=$([[ $((n%2)) == 0 ]] && echo Release || echo Debug) >/dev/null; run --build build --parallel 2 >/dev/null; run --build build --target test >/dev/null; touch src/calc.c; ((++n)); done
    ;;
  python3)
    run - "$duration" <<'PY'
import hashlib,json,sqlite3,sys,tempfile,time,zlib
end=time.monotonic()+int(sys.argv[1]); db=sqlite3.connect('work.db'); db.execute('create table if not exists records(k integer,v text)'); n=0
while time.monotonic()<end:
 data=[{'id':i,'value':hashlib.sha256(f'{n}:{i}'.encode()).hexdigest()} for i in range(2000)]
 blob=zlib.compress(json.dumps(data).encode()); assert len(zlib.decompress(blob))>len(blob)
 db.executemany('insert into records values(?,?)',((x['id'],x['value']) for x in data)); db.commit(); db.execute('delete from records'); n+=1
print(n)
PY
    ;;
  perl)
    run -MTime::HiRes=time -MDigest::SHA=sha256_hex -MJSON::PP=encode_json -e '$e=time()+shift; $n=0; while(time()<$e){@a=map{{id=>$_,value=>sha256_hex("$n:$_")}}0..1999; $j=encode_json(\@a); open(F,">batch.dat")or die$!; print F $j; close F; open(F,"<batch.dat"); local $/=undef; $x=<F>; close F; die unless length($x)==length($j); $n++} print "$n\n"' "$duration" >output
    ;;
  ruby)
    # Stay within Ruby's core runtime: some distribution packages split the
    # standard-library JSON and digest modules into separate packages.
    run -e 'finish=Process.clock_gettime(Process::CLOCK_MONOTONIC)+ARGV[0].to_i;n=0;while Process.clock_gettime(Process::CLOCK_MONOTONIC)<finish;a=20000.times.map{|i|[(i*1103515245+n)&0x7fffffff,"record-#{n}-#{i}"]};a.sort_by!{|x|x[0]};text=a.map{|x|x.join(":")}.join("\n");File.binwrite("batch.txt",text);lines=File.foreach("batch.txt").grep(/record-/);raise unless lines.size==20000;n+=1;end;puts n' "$duration" >output
    ;;
  node)
    run - "$duration" <<'JS'
const fs=require('fs'),crypto=require('crypto'),zlib=require('zlib'); const end=process.hrtime.bigint()+BigInt(process.argv[2])*1000000000n; let n=0;
while(process.hrtime.bigint()<end){let a=Array.from({length:2000},(_,i)=>({id:i,value:crypto.createHash('sha256').update(`${n}:${i}`).digest('hex')}));let b=zlib.gzipSync(JSON.stringify(a));fs.writeFileSync('batch.gz',b);if(JSON.parse(zlib.gunzipSync(fs.readFileSync('batch.gz'))).length!==2000)throw Error('bad');n++} console.log(n)
JS
    ;;
  npm)
    mkdir -p dep app; printf '{"name":"local-dep","version":"1.0.0","main":"index.js"}\n' >dep/package.json; printf 'module.exports=x=>x*x\n' >dep/index.js
    printf '{"name":"small-app","version":"1.0.0","private":true,"scripts":{"test":"node test.js"},"dependencies":{"local-dep":"file:../dep"}}\n' >app/package.json; printf 'const f=require("local-dep");if(f(9)!==81)process.exit(1)\n' >app/test.js
    n=0; while active; do (cd app && run install --offline --ignore-scripts --no-audit --no-fund >/dev/null && run test --offline >/dev/null && run pack --offline --ignore-scripts --pack-destination .. >/dev/null); rm -rf app/node_modules app/package-lock.json ./*.tgz; ((++n)); done
    ;;
  java|javac)
    cat >Work.java <<'JAVA'
import java.nio.file.*;import java.security.*;import java.util.*;public class Work{static String hex(byte[]b){char[]d="0123456789abcdef".toCharArray(),r=new char[b.length*2];for(int i=0;i<b.length;i++){int v=b[i]&255;r[i*2]=d[v>>>4];r[i*2+1]=d[v&15];}return new String(r);}public static void main(String[]a)throws Exception{long e=System.nanoTime()+Long.parseLong(a[0])*1000000000L;int n=0;var d=MessageDigest.getInstance("SHA-256");while(System.nanoTime()<e){var v=new ArrayList<String>();for(int i=0;i<20000;i++)v.add(hex(d.digest((n+":"+i).getBytes())));Collections.sort(v);Files.write(Path.of("batch.txt"),v);n++;}System.out.println(n);}}
JAVA
    if [[ $tool == javac ]]; then run -g -Xlint:all Work.java; java Work "$duration" >output
    else run Work.java "$duration" >output; fi
    ;;
  go)
    cat >go.mod <<'EOF'; mkdir -p work
module example.invalid/small
go 1.20
EOF
    cat >work/work.go <<'EOF'
package work
import("crypto/sha256";"encoding/json";"os";"sort")
func Run(n int)error{v:=make([][32]byte,10000);for i:=range v{v[i]=sha256.Sum256([]byte{byte(n),byte(i)})};sort.Slice(v,func(i,j int)bool{return string(v[i][:])<string(v[j][:])});b,_:=json.Marshal(v);return os.WriteFile("batch.json",b,0600)}
EOF
    printf 'package work\nimport "testing"\nfunc TestRun(t *testing.T){if Run(3)!=nil{t.Fatal("run")}}\n' >work/work_test.go
    n=0; while active; do GOCACHE="$case_dir/cache" GOPATH="$case_dir/gopath" run test -count=1 ./... >/dev/null; GOCACHE="$case_dir/cache" GOPATH="$case_dir/gopath" run build ./...; ((++n)); done
    ;;
  cargo)
    mkdir src; printf '[package]\nname="small"\nversion="0.1.0"\nedition="2021"\n' >Cargo.toml
    printf 'pub fn work(n:u64)->u64{(0..100000).map(|x|x^n).sum()}\n#[cfg(test)]mod tests{#[test]fn works(){assert!(super::work(3)>0)}}\n' >src/lib.rs
    n=0; while active; do CARGO_HOME="$case_dir/home" CARGO_TARGET_DIR="$case_dir/target" run test --offline --quiet; CARGO_HOME="$case_dir/home" CARGO_TARGET_DIR="$case_dir/target" run build --offline --release --quiet; touch src/lib.rs; ((++n)); done
    ;;
  rustc)
    printf 'use std::{env,fs,time::{Duration,Instant}};fn main(){let e=Instant::now()+Duration::from_secs(env::args().nth(1).unwrap().parse().unwrap());let mut n=0;while Instant::now()<e{let mut v:Vec<_>=(0..200000).map(|x|x^n).collect();v.sort_unstable();fs::write("batch",format!("{:?}",v)).unwrap();n+=1}println!("{}",n)}\n' >work.rs
    run -O -g work.rs -o work; ./work "$duration" >output
    ;;
  docker)
    export DOCKER_CONFIG="$case_dir/docker-config"; mkdir -p "$DOCKER_CONFIG"
    n=0; while active; do run context create "ctx$n" --docker "host=unix://$case_dir/nonexistent.sock" >/dev/null; run context inspect "ctx$n" >inspect.json; run context use "ctx$n" >/dev/null; run context export "ctx$n" >context.tar; run context use default >/dev/null; run context rm -f "ctx$n" >/dev/null; ((++n)); done
    ;;
  podman)
    export HOME="$case_dir/home" XDG_RUNTIME_DIR="$case_dir/run"; mkdir -p "$HOME" "$XDG_RUNTIME_DIR"; chmod 700 "$XDG_RUNTIME_DIR"
    # Exercise the normal remote-client configuration workflow without needing
    # a privileged local container store or contacting an external service.
    n=0; while active; do name="local-$n"; run system connection add "$name" "unix://$case_dir/nonexistent-$n.sock" >/dev/null; run system connection list --format json >connections.json; run system connection default "$name"; run system connection remove "$name" >/dev/null; ((++n)); done
    ;;
  kubectl)
    : >kubeconfig; mkdir manifests
    cat >manifests/app.yaml <<'EOF'
apiVersion: v1
kind: ConfigMap
metadata: {name: small-config, namespace: default}
data: {mode: test}
---
apiVersion: apps/v1
kind: Deployment
metadata: {name: small}
spec: {replicas: 2, selector: {matchLabels: {app: small}}, template: {metadata: {labels: {app: small}}, spec: {containers: [{name: app, image: example.invalid/app:1}]}}}
EOF
    n=0; while active; do KUBECONFIG="$case_dir/kubeconfig" run create configmap small-config --from-file=manifests/app.yaml --from-literal="iteration=$n" --dry-run=client -o json >objects.json; KUBECONFIG="$case_dir/kubeconfig" run create deployment small --image=example.invalid/app:1 --replicas=$((n%5+1)) --dry-run=client -o yaml >deployment.yaml; KUBECONFIG="$case_dir/kubeconfig" run config view --raw --flatten >config.yaml; ((++n)); done
    ;;
  helm)
    mkdir -p chart/templates packages; printf 'apiVersion: v2\nname: small\nversion: 1.0.0\n' >chart/Chart.yaml; printf 'replicas: 2\nimage: example.invalid/app:1\n' >chart/values.yaml
    cat >chart/templates/deployment.yaml <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata: {name: {{ .Release.Name }}}
spec:
  replicas: {{ .Values.replicas }}
  selector: {matchLabels: {app: {{ .Release.Name }}}}
  template: {metadata: {labels: {app: {{ .Release.Name }}}}, spec: {containers: [{name: app, image: {{ .Values.image }} }]}}
EOF
    n=0; while active; do run lint chart >/dev/null; run template "small-$n" chart --set replicas=$((n%5+1)) >rendered.yaml; run package chart --destination packages >/dev/null; run show values packages/small-1.0.0.tgz >shown.yaml; ((++n)); done
    ;;
  jq)
    run -n '[range(0;20000)|{id:.,group:(.%17),value:(.*.)}]' >input.json
    n=0; while active; do run '[group_by(.group)[]|{group:.[0].group,count:length,total:(map(.value)|add)}]|sort_by(-.total)' input.json >report.json; run -s 'flatten|unique_by(.id)|map(select(.value>1000))' input.json report.json >filtered.json; ((++n)); done
    ;;
  yq)
    mkdir docs; for i in {1..40}; do printf 'service:\n  name: service-%s\n  port: %s\n  enabled: true\n' "$i" "$((8000+i))" >"docs/$i.yaml"; done
    if run eval '.service.name' docs/1.yaml >/dev/null 2>&1; then yq_flavor=mike; else yq_flavor=python; fi
    n=0; while active; do
      if [[ $yq_flavor == mike ]]; then
        run eval-all '. as $item ireduce ([]; . + [$item.service]) | {"services": .}' docs/*.yaml >merged.yaml
        run '.services |= map(.port += 100 | .enabled = (.port % 2 == 0))' merged.yaml >transformed.yaml
      else
        run -y -s '{"services": map(.service)} | .services |= map(.port += 100 | .enabled = (.port % 2 == 0))' docs/*.yaml >transformed.yaml
        run -y '.services | sort_by(.port) | {"count": length, "enabled": map(select(.enabled)), "services": .}' transformed.yaml >merged.yaml
      fi
      ((++n))
    done
    ;;
  tmux)
    sock="small-$$"; trap '"$executable" -L "$sock" kill-server 2>/dev/null || true' EXIT
    run -L "$sock" new-session -d -s work; n=0
    while active; do run -L "$sock" new-window -d -n "job$n" "bash --noprofile --norc -c 'i=0; while [ \$i -lt 10000 ]; do i=\$((i+1)); done; printf %s $n > job-$n'"; run -L "$sock" list-windows -a -F '#{session_name}:#{window_index}:#{window_name}:#{pane_pid}' >windows; run -L "$sock" capture-pane -p -t work:0 >capture; (( n % 8 )) || run -L "$sock" kill-window -t work:1 2>/dev/null || true; ((++n)); done
    run -L "$sock" kill-server; trap - EXIT
    ;;
  screen)
    export SCREENDIR="$case_dir/sockets"; mkdir -m 700 "$SCREENDIR"
    printf 'defscrollback 2000\ndefutf8 on\nstartup_message off\nlogfile %s/screen.log\n' "$case_dir" >screenrc
    # Foreground detached mode lets screen own and supervise a real pseudo-TTY
    # workload while still returning deterministically when the job is done.
    run -D -m -L -c "$case_dir/screenrc" -S "small-$$" bash --noprofile --norc -c 'end=$((SECONDS+$1)); n=0; while ((SECONDS<end)); do find . -maxdepth 2 -type f -printf "%p %s\n" | sort | sha256sum >activity.next; mv activity.next activity; printf "batch %s complete\n" "$n"; n=$((n+1)); done' bash "$duration"
    ;;
  strace)
    # A process cannot have two ptrace tracers.  During a traced harness run the
    # prefix-installed strace is already the outer CSB collector, so exercise
    # it by keeping that collector busy with representative file/process work.
    # Direct --no-trace runs still use the selected strace as a nested tracer.
    tracer_pid=$(awk '/^TracerPid:/ {print $2}' /proc/self/status)
    n=0
    while active; do
      if (( tracer_pid > 0 )); then
        bash --noprofile --norc -c 'mkdir -p tree; printf data >tree/input; cp tree/input tree/copy; mv tree/copy tree/final; cat tree/final >/dev/null; rm tree/final'
      else
        run -ff -qq -o "trace-$n" -e trace=%file,%process,%network bash --noprofile --norc -c 'mkdir -p tree; printf data >tree/input; cp tree/input tree/copy; mv tree/copy tree/final; cat tree/final >/dev/null; rm tree/final'
      fi
      ((++n))
    done
    ;;
  lsof)
    mkdir tree; printf '{"fixture":"lsof-small"}\n' >input.json
    exec 8>tree/write.log; exec 9<input.json
    n=0; while active; do
      # -b avoids blocking stat/readlink calls across unrelated host mounts.
      run -b -n -P -a -p $$ -d cwd,0-9 -F pcftn >process-files 2>/dev/null || true
      run -b -n -P "$case_dir/tree/write.log" -F pcftn >local-file 2>/dev/null || true
      ((++n))
    done
    ;;
  tcpdump)
    filters=('tcp port 22' 'udp and port 53' 'icmp or icmp6' 'host 127.0.0.1' 'tcp[tcpflags] & tcp-syn != 0' 'greater 512')
    n=0; while active; do for f in "${filters[@]}"; do run -d "$f" >"filter-$((n%8)).bpf"; run -ddd "$f" >>"filter-$((n%8)).bpf"; active || break; done; ((++n)); done
    ;;
  perf)
    n=0; while active; do run stat -o "stat-$((n%8)).txt" -e task-clock,context-switches,cpu-migrations,page-faults -- bash --noprofile --norc -c 'i=0; while [ "$i" -lt 200000 ]; do i=$((i+1)); done' 2>/dev/null || run stat -o "stat-$((n%8)).txt" -- true 2>/dev/null || true; ((++n)); done
    ;;
  time)
    n=0; while active; do run -v -o "time-$((n%8)).txt" bash --noprofile --norc -c 'i=0; : > work; while [ "$i" -lt 50000 ]; do printf "%s\n" "$i" >>work; i=$((i+1)); done; sort -n work >sorted' 2>/dev/null; ((++n)); done
    ;;
  watch)
    printf '0\n' >counter; (while active; do awk '{print $1+1}' counter >next; mv next counter; sha256sum counter >digest; done) & producer=$!
    trap 'kill "$producer" 2>/dev/null || true' EXIT
    while active; do
      # --chgexit makes each foreground watch exit after the producer changes
      # the displayed state, avoiding detached descendants under strace.
      run --chgexit -n 0.2 -t -x bash --noprofile --norc -c 'printf "counter="; cat counter; printf "files="; find . -type f | wc -l; cat digest' >>watch.out 2>&1 || true
    done
    kill "$producer" 2>/dev/null || true; wait "$producer" 2>/dev/null || true; trap - EXIT
    ;;
  *) printf 'no small workload for %s\n' "$tool" >&2; exit 1;;
esac
