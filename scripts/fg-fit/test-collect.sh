#!/usr/bin/bash
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/bin" "$tmp/flamegraph"

cat > "$tmp/bin/strace" <<'EOF'
#!/bin/sh
if [ "$1" = "-V" ]; then echo "strace test"; exit; fi
while [ "$1" != "-o" ]; do shift; done
printf 'test trace\n' > "$2"
EOF
cat > "$tmp/bin/perf" <<'EOF'
#!/bin/sh
case "$1" in
version) echo "perf test" ;;
record) while [ "$1" != "-o" ]; do shift; done; : > "$2" ;;
script) printf 'demo 1 0 cycles:\n ffffffff kernel_fn ([kernel.kallsyms])\n\n' ;;
esac
EOF
cat > "$tmp/flamegraph/stackcollapse-perf.pl" <<'EOF'
#!/bin/sh
cat >/dev/null
echo 'THR;kernel_fn 1'
EOF
chmod +x "$tmp/bin/strace" "$tmp/bin/perf" "$tmp/flamegraph/stackcollapse-perf.pl"

PATH="$tmp/bin:$PATH" PERF=perf FLAMEGRAPH="$tmp/flamegraph" \
    "$root/scripts/fg-fit/collect.sh" --output "$tmp/capture" --target demo -- /bin/true

test -s "$tmp/capture/trace.strace"
test -s "$tmp/capture/trace.strace.meta"
test -f "$tmp/capture/perf.data"
test -s "$tmp/capture/perf.script"
grep -q '^kernel_fn 1$' "$tmp/capture/reference.stacks"
grep -q '^csb.capture.target=demo$' "$tmp/capture/capture.meta"
echo "collector test passed"
