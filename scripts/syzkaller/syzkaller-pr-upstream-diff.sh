#!/usr/bin/env bash
set -euo pipefail

pr=${1:-149}
repo=${2:-deps/syzkaller}
out=${3:-syzkaller-pr${pr}-modified-only.diff}
pr_ref="refs/codex/pr${pr}-head"
upstream_ref=refs/codex/google-master

git -C "$repo" fetch --no-tags --force https://github.com/open-s4c/syzkaller.git \
	"refs/pull/${pr}/head:${pr_ref}"
git -C "$repo" fetch --no-tags --force https://github.com/google/syzkaller.git \
	"refs/heads/master:${upstream_ref}"

head=$(git -C "$repo" rev-parse "$pr_ref")
base=$(git -C "$repo" merge-base "$head" "$upstream_ref")
git -C "$repo" -c diff.renames=false diff --no-renames --full-index --binary \
	--diff-filter=M "$base" "$head" -- . \
	':(exclude)tools/syz-trace2syz/parser/lex.go' \
	':(exclude)tools/syz-trace2syz/parser/strace.go' >"$out"

printf 'base=%s\nhead=%s\ndiff=%s\n' "$base" "$head" "$out"
