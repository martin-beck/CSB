#!/usr/bin/env bash
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT
# Realistic, bounded "small" workloads for tools 35--67.
set -Eeuo pipefail

[[ $# == 4 ]] || { printf 'usage: %s TOOL EXECUTABLE CASE_DIR DURATION\n' "$0" >&2; exit 2; }
tool=$1 executable=$2 case_dir=$3 duration=$4
[[ -x "$executable" ]] || { printf 'not executable: %s\n' "$executable" >&2; exit 1; }
[[ -d "$case_dir" && "$case_dir" != / && "$case_dir" != "$HOME" ]] || {
	printf 'unsafe case directory\n' >&2; exit 1;
}
[[ "$duration" =~ ^[1-9][0-9]*$ ]] || { printf 'DURATION must be a positive integer\n' >&2; exit 2; }
cd -- "$case_dir"

run() { command "$executable" "$@"; }
start_us=${EPOCHREALTIME/./}
deadline_us=$((10#$start_us + duration * 1000000))
keep_running() {
	local now_us=${EPOCHREALTIME/./}
	(( 10#$now_us < deadline_us ))
}
try() { "$@" || true; }
start_http_server() {
	# python3 is another corpus-installed command resolved from PREFIX-first PATH;
	# it supplies a loopback-only peer so transfer clients perform successful HTTP.
	local python
	python=$(command -v python3) || { printf 'prefix python3 is required for the transfer workload\n' >&2; return 1; }
	http_port=$((20000 + BASHPID % 20000))
	"$python" -m http.server "$http_port" --bind 127.0.0.1 --directory "$case_dir/source" >http-server.log 2>&1 &
	http_pid=$!
	trap 'kill "$http_pid" 2>/dev/null || true; wait "$http_pid" 2>/dev/null || true' EXIT
}
stop_http_server() {
	kill "$http_pid" 2>/dev/null || true
	wait "$http_pid" 2>/dev/null || true
	trap - EXIT
}

# A moderately varied local data set, large enough to exercise buffers, parsing,
# archive indexes and directory walking without consuming unbounded disk space.
mkdir -p source/{docs,logs,data,empty}
for ((n=0; n<256; n++)); do
	printf 'record=%04d class=%d words=alpha,beta,gamma payload=%08x\n' \
		"$n" "$((n % 11))" "$((n * 2654435761 & 0xffffffff))" >>source/data/records.txt
	printf '%04d INFO worker=%d request=/item/%d status=%d\n' \
		"$n" "$((n % 8))" "$n" "$((200 + n % 5))" >>source/logs/service.log
done
printf '# Example project\n\nneedle: alpha\n\nA local workload fixture.\n' >source/docs/README.md
for ((n=0; n<24; n++)); do printf 'file %d\n' "$n" >"source/docs/note-$n.txt"; done

case "$tool" in
zip)
	i=0; while keep_running; do
		run -q -r "archive-$((i % 3)).zip" source -x '*/empty/*'
		# zip returns 12 when an update finds nothing newer; that is a successful
		# no-change incremental backup pass for this workload.
		try run -q -u "archive-$((i % 3)).zip" source/docs/README.md
		run -sf "archive-$((i % 3)).zip" >archive-index.txt
		((++i))
	done ;;
unzip)
	# A complete stored ZIP containing hello.txt, emitted with the shell builtin so
	# unzip itself remains the only corpus executable needed by this workload.
	printf '\x50\x4b\x03\x04\x0a\x00\x00\x00\x00\x00\x44\x57\xf7\x5c\x20\x30\x3a\x36\x06\x00\x00\x00\x06\x00\x00\x00\x09\x00\x00\x00\x68\x65\x6c\x6c\x6f\x2e\x74\x78\x74\x68\x65\x6c\x6c\x6f\x0a\x50\x4b\x01\x02\x1e\x03\x0a\x00\x00\x00\x00\x00\x44\x57\xf7\x5c\x20\x30\x3a\x36\x06\x00\x00\x00\x06\x00\x00\x00\x09\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xb4\x81\x00\x00\x00\x00\x68\x65\x6c\x6c\x6f\x2e\x74\x78\x74\x50\x4b\x05\x06\x00\x00\x00\x00\x01\x00\x01\x00\x37\x00\x00\x00\x2d\x00\x00\x00\x00\x00' >sample.zip
	i=0; while keep_running; do
		mkdir -p "extract-$((i % 3))"
		try run -t sample.zip >archive-test.txt 2>&1
		try run -o sample.zip -d "extract-$((i % 3))" >extract.log 2>&1
		try run -Z -v sample.zip >archive-report.txt 2>&1
		((++i))
	done ;;
diff)
	cp source/data/records.txt left.txt; cp source/data/records.txt right.txt
	printf 'record=changed class=9 words=delta\n' >>right.txt
	i=0; while keep_running; do
		try run -u --label old --label new left.txt right.txt >change.patch
		try run -y --suppress-common-lines left.txt right.txt >side-by-side.txt
		try run -qr source source-copy >tree-diff.txt
		((++i)); printf 'iteration=%d\n' "$i" >>right.txt
	done ;;
patch)
	i=0; while keep_running; do
		printf 'line one\nline old\nline three\n' >target.txt
		printf '%s\n' '--- target.txt' '+++ target.txt' '@@ -1,3 +1,4 @@' ' line one' '-line old' '+line new' '+inserted line' ' line three' >change.patch
		run --batch --forward <change.patch >patch.log
		run --batch -R <change.patch >>patch.log
		run --dry-run --batch <change.patch >>patch.log
		((++i))
	done ;;
less)
	i=0; while keep_running; do
		run -F -X -S -N +/worker=7 source/logs/service.log >page.txt
		run -F -X +G source/data/records.txt >tail-page.txt
		((++i))
	done ;;
vi)
	i=0; while keep_running; do
		cp source/docs/README.md edit.txt
		printf '%s\n' '%s/alpha/ALPHA/g' '1i' "edited iteration $i" '.' '$a' 'footer' '.' 'wq' >commands.ex
		run -Nu NONE -n -es edit.txt <commands.ex
		((++i))
	done ;;
nano)
	i=0; while keep_running; do
		printf 'set linenumbers\nset tabsize %d\nsyntax "logs" "\\.log$"\ncolor brightgreen "INFO"\n' "$((2 + i % 7))" >nanorc
		try run --ignorercfiles --lint nanorc >nano-lint.txt 2>&1
		printf 'include "%s/nanorc"\n' "$case_dir" >main.nanorc
		try run --ignorercfiles --lint main.nanorc >>nano-lint.txt 2>&1
		((++i))
	done ;;
ps)
	while keep_running; do
		run -eo user,pid,ppid,stat,etimes,pcpu,pmem,comm --sort=-pcpu >processes.txt
		run -e --forest -o pid,ppid,tty,stat,args >process-tree.txt
		run -p $$ -o pid=,lstart=,args= >self.txt
	done ;;
top)
	while keep_running; do
		run -b -n 1 -w 160 -o %CPU >top-cpu.txt
		run -b -n 1 -w 160 -o %MEM >top-memory.txt
	done ;;
free)
	while keep_running; do run -w -h >memory-human.txt; run -w -b >memory-bytes.txt; run -s 0.1 -c 2 >memory-samples.txt; done ;;
uptime)
	while keep_running; do run -p >uptime-pretty.txt; run -s >boot-time.txt; run >load.txt; done ;;
uname)
	while keep_running; do run -a >all.txt; run -srmv >kernel.txt; run -m -p -i >architecture.txt; done ;;
hostname)
	while keep_running; do run >hostname.txt; try run -f >fqdn.txt; try run -i >addresses.txt; try run -d >domain.txt; done ;;
id)
	while keep_running; do run >identity.txt; run -u >uid.txt; run -g >gid.txt; run -G >groups.txt; run -un >user.txt; done ;;
whoami)
	while keep_running; do run >current-user.txt; done ;;
groups)
	while keep_running; do run >memberships.txt; try run "${USER:-$(run)}" >named-memberships.txt; done ;;
df)
	while keep_running; do run -P "$case_dir" >filesystem-posix.txt; run -hT "$case_dir" >filesystem-types.txt; run -i "$case_dir" >inodes.txt; done ;;
du)
	while keep_running; do run -a -b source >usage-all.txt; run -s -h source >usage-summary.txt; run --max-depth=2 source >usage-depth.txt; done ;;
lsblk)
	while keep_running; do try run -J -b -O >block-all.json; try run -P -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINTS >block-pairs.txt; try run -T >block-tree.txt; done ;;
lscpu)
	while keep_running; do run >cpu.txt; run -J >cpu.json; try run -e=CPU,NODE,SOCKET,CORE,CACHE,ONLINE >cpu-table.txt; try run -C=NAME,ONE-SIZE,ALL-SIZE,TYPE,LEVEL >cache-table.txt; done ;;
mount)
	while keep_running; do run >mounts.txt; try run -l -t proc,sysfs,tmpfs >virtual-mounts.txt; try run --all --fake --verbose >fake-mount-check.txt 2>&1; done ;;
dmesg)
	while keep_running; do try run --color=never --level=emerg,alert,crit,err,warn >kernel-warnings.txt 2>&1; try run --ctime --decode >kernel-decoded.txt 2>&1; try run --show-delta --userspace >userspace-messages.txt 2>&1; done ;;
journalctl)
	while keep_running; do try run --no-pager -n 200 -o short-iso >recent.log 2>&1; try run --no-pager --since '-1 hour' -p warning -o json >warnings.json 2>&1; try run --no-pager --disk-usage >journal-size.txt 2>&1; done ;;
systemctl)
	while keep_running; do try run --no-pager --no-legend list-units --all --type=service >services.txt 2>&1; try run --no-pager list-unit-files >unit-files.txt 2>&1; try run --no-pager show --property=Version,Features >manager.txt 2>&1; done ;;
ip)
	while keep_running; do run -details -statistics address show >addresses.txt; run -details route show table all >routes.txt; run -statistics link show >links.txt; run -json neighbor show >neighbors.json; done ;;
ss)
	while keep_running; do run -H -a -n -t -u >internet-sockets.txt; run -H -a -n -x >unix-sockets.txt; try run -H -s >socket-summary.txt; try run -H -l -n -p >listeners.txt 2>&1; done ;;
ping)
	while keep_running; do try run -n -c 4 -W 1 -s 56 127.0.0.1 >ping-small.txt; try run -n -c 2 -W 1 -s 1200 127.0.0.1 >ping-large.txt; done ;;
traceroute)
	while keep_running; do try run -n -m 4 -q 2 -w 1 127.0.0.1 >route-udp.txt 2>&1; try run -n -I -m 4 -q 1 -w 1 127.0.0.1 >route-icmp.txt 2>&1; done ;;
curl)
	start_http_server
	i=0; while keep_running; do
		try run --fail --silent --show-error --compressed "http://127.0.0.1:${http_port}/data/records.txt" -o "download-$((i % 3)).txt"
		try run --fail --silent --range 32-511 "http://127.0.0.1:${http_port}/logs/service.log" -o range.txt
		try run --fail --silent --head "http://127.0.0.1:${http_port}/docs/README.md" >headers.txt
		((++i))
	done
	stop_http_server ;;
wget)
	start_http_server
	while keep_running; do
		try run --timeout=1 --tries=2 --server-response -O fetched.txt "http://127.0.0.1:${http_port}/data/records.txt" >wget.log 2>&1
		try run --spider --timeout=1 --tries=2 "http://127.0.0.1:${http_port}/docs/README.md" >>wget.log 2>&1
	done
	stop_http_server ;;
ssh)
	cat >ssh_config <<-EOF
	Host local-test
	  HostName 127.0.0.1
	  Port 9
	  User trace
	  ConnectTimeout 1
	  BatchMode yes
	  StrictHostKeyChecking no
	  UserKnownHostsFile $case_dir/known_hosts
	  ControlMaster no
	EOF
	while keep_running; do
		run -T -F ssh_config -G local-test >resolved-config.txt 2>&1
		try run -T -F ssh_config -vv local-test true >session.log 2>&1
		try run -F ssh_config -Q cipher >ciphers.txt
	done ;;
scp)
	cat >ssh_config <<-EOF
	Host local-test
	  HostName 127.0.0.1
	  Port 9
	  User trace
	  ConnectTimeout 1
	  BatchMode yes
	  StrictHostKeyChecking no
	  UserKnownHostsFile $case_dir/known_hosts
	EOF
	while keep_running; do
		try run -F ssh_config -vv -p -r source local-test:/tmp/csb-trace >copy.log 2>&1
		try run -F ssh_config -vv local-test:/tmp/csb-trace/README.md received.txt >>copy.log 2>&1
	done ;;
rsync)
	i=0; while keep_running; do
		mkdir -p mirror
		run -a --delete --checksum --itemize-changes source/ mirror/ >changes.txt
		printf 'iteration=%d\n' "$i" >>source/logs/service.log
		run -a --delete --checksum --link-dest="$case_dir/mirror" source/ "snapshot-$((i % 3))/" >>changes.txt
		run -a -n --stats source/ mirror/ >sync-stats.txt
		((++i))
	done ;;
*)
	printf 'small-2 has no workload for %s\n' "$tool" >&2
	exit 1 ;;
esac
