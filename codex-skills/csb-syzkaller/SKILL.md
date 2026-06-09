---
name: csb-syzkaller
description: "Use when working on CSB's deps/syzkaller fork or bm-generator pipeline: parsing strace logs into syzlang programs, extracting/minimizing syscall programs, converting syz programs into CSB C headers, generating benchmark JSON configs, debugging generated microbenchmarks, or validating the Go/tool build environment. Do not use for ordinary CSB runner/config work unless syzkaller-generated benchmarks are involved."
---

# CSB Syzkaller Generator

This skill covers the CSB-specific syzkaller fork under `deps/syzkaller` and the CSB `bm-generator/` scripts that turn captured `strace` logs into runnable CSB microbenchmarks.

## Boundaries

- Treat `deps/syzkaller` as its own git repository/submodule. Check its status and history separately from the CSB root.
- Use the general `csb` skill for `bm-runner/`, normal benchmark configs, monitors, plots, and container/native execution behavior.
- Use this skill when the work touches syzkaller tools, syzlang `.prog` files, generated headers under `bench/targets/<group>/syz`, or generated configs under `config/<group>`.
- Generated benchmark artifacts are often untracked. Do not delete or overwrite them unless the user asked for regeneration or cleanup.

## First Checks

From the CSB root:

```bash
git status --short
git -C deps/syzkaller status --short
git -C deps/syzkaller log --oneline --decorate --max-count=50
rg --files bm-generator deps/syzkaller/tools/syz-trace2syz deps/syzkaller/tools/syz-extraction deps/syzkaller/tools/syz-prog2c deps/syzkaller/prog deps/syzkaller/pkg/csource
```

For code search, focus first on:

```bash
rg '<term>' bm-generator deps/syzkaller/tools/syz-trace2syz deps/syzkaller/tools/syz-extraction deps/syzkaller/tools/syz-prog2c deps/syzkaller/prog deps/syzkaller/pkg/csource
```

## Fork Purpose

The fork is an end-to-end microbenchmark generator for captured program executions:

1. parse `strace` logs into syzlang programs;
2. preserve strace thread IDs and syscall return values in `.prog` serialization;
3. extract smaller syscall programs that resemble kernel task slices from the captured execution;
4. sanitize paths, file descriptors, socket/network arguments, buffers, and unsupported calls so generated programs can replay as benchmarks;
5. convert syzlang programs into CSB C headers;
6. generate JSON configuration files that let CSB run those headers as automatic benchmarks.

The CSB commit series starts at `f267c75ad Enables CSB generation` and, through `252d6d55b`, adds CSB C generation, strace return/TID annotations, faster dependency-based extraction, deterministic thread ordering, network-server extraction support, metadata generation, FD leak handling, path/bind/connect sanitization, write-buffer alignment, and build/test workflow fixes.

## Generator Pipeline

Run numbered scripts from `bm-generator/`.

```bash
cd bm-generator
./00_init.sh
./01_build.sh
./02_parse.sh /path/to/strace.log
./03_extract.sh
./04_prepare.sh
./05_generate.sh
./06_select.sh
```

Important environment variables:

- `DIR_SYZ_SRC`: syzkaller source directory; defaults to `../build/syzkaller-path.txt` via `helper/find_syzkaller_src.sh`.
- `DIR_PROG`: input/output `.prog` directory depending on step; defaults to `./deserialized` for parse/extract input and `./extracted` for prepare input.
- `DIR_OUT`: extraction output directory; defaults to `./extracted`.
- `MINCALLS`: minimum calls retained by `syz-extraction`; defaults to `10` in `03_extract.sh`.
- `JOBS`: parallelism; defaults to `nproc`.
- `CSB_RESULTS_GROUP`: workspace/group name for generated targets/config/results; defaults to `gen-ws`.

Pipeline details:

- `00_init.sh` requires Go >= 1.25 and can call `helper/install_go.sh`.
- `01_build.sh` checks `go env GOBIN`, configures CSB with `CSB_BM_GENERATOR=ON` if needed, then builds the syzkaller tools through CMake.
- `02_parse.sh` requires an empty deserialization directory and runs `bin/syz-trace2syz -vv 0 -file <trace> --deserialize <dir> --nocorpus`, then compares syscall distributions with `helper/compare_strace_to_syzprog.sh`.
- `03_extract.sh` runs `bin/syz-extraction -prog <file> -deserialize <dir> -minCalls <MINCALLS>` for each parsed program and prunes empty output directories.
- `04_prepare.sh` converts each extracted `.prog` with `helper/prog2bm.sh`, which runs `bin/syz-prog2c -csb -trace=true -format=false -prog <prog> -cfile ../bench/targets/<group>/syz/<name>.h`.
- `05_generate.sh` builds template targets `syz_single.h.in` and `bm_single.json.in`, producing C headers/configs through the CSB template machinery.
- `06_select.sh` runs generated configs through flamegraph-based selection and merges selected benchmarks.

## Syzkaller Areas

Core CSB changes live in:

- `tools/syz-trace2syz/`: strace lexer/parser/proggen changes, `-deserialize`, `-nocorpus`, `-topCalls`, `-splitThreads`, and `-argLength`.
- `prog/`: serialization of strace TID as `<tid>` and syscall return as `[ret]`, cloning annotations, call dependency annotations, and extraction-oriented minimization.
- `tools/syz-extraction/`: extraction CLI, dependency minimization, poll filtering, minimum program size, deterministic TID iteration, and network-server split handling.
- `tools/syz-prog2c/` and `pkg/csource/`: `-csb` header generation, syscall tracing, path/socket/file sanitization, FD leak handling, shared write/send buffers, metadata, and CSB benchmark config output.
- `executor/common*.h` and `sys/linux/sys.txt*`: runtime helpers and syscall description adjustments needed by generated C.
- `Makefile`: CSB tool targets `trace2syz`, `prog2c`, and `extraction`.

When changing parser syntax, check whether generated parser files need regeneration:

```bash
cd deps/syzkaller
make generate_trace2syz
```

## Build And Tests

For operational validation, build the tools from `deps/syzkaller`:

```bash
cd deps/syzkaller
make trace2syz prog2c extraction
```

Useful focused Go tests:

```bash
cd deps/syzkaller
go test ./tools/syz-trace2syz/parser ./tools/syz-trace2syz/proggen
go test ./prog ./pkg/csource
go test ./tools/syz-extraction ./tools/syz-prog2c ./tools/syz-trace2syz
```

Full syzkaller tests:

```bash
cd deps/syzkaller
make test
```

Environment notes:

- The current CSB workflow expects Go 1.25 or newer. `00_init.sh` checks this.
- Syzkaller's Makefile sets `GOBIN` to `deps/syzkaller/bin` while building tools.
- Plain `go test` uses the user's normal `GOCACHE`, `GOMODCACHE`, and compiler caches. In sandboxed environments this may require approval if caches such as `~/.ccache` are not writable.
- Syzkaller's Makefile warns that `tools/syz-env` is preferred for upstream compatibility; report this warning, but it is not itself a failure.
- On the current fork, tool builds can pass while some legacy upstream tests fail because tests still expect old function signatures or serialization without CSB `[ret]` annotations. Treat those as test-suite drift unless the user is specifically asking to repair tests.

## Generated Output Checks

After a generation run, inspect:

```bash
find bm-generator/deserialized bm-generator/extracted -name '*.prog' | head
find bench/targets/"${CSB_RESULTS_GROUP:-gen-ws}"/syz -name '*.h' | head
find config/"${CSB_RESULTS_GROUP:-gen-ws}" -name '*.json' | head
```

Sanity checks:

- `.prog` names are derived from the trace filename prefix and top syscall names.
- Extracted files are named `min_<prefix>_<top-calls>_<index>.prog`.
- Generated headers should live under `bench/targets/<group>/syz`.
- Generated configs should reference the generated benchmark names and keep CSB `operations` totals valid.
- `compare_strace_to_syzprog.sh` reports syscall coverage and lost syscall names after parsing.

## Common Failure Modes

- `DIR_PROG` not empty in `02_parse.sh`: move or clean the output directory before parsing.
- Syzkaller source not found: run `01_build.sh`, configure CSB with `CSB_BM_GENERATOR=ON`, or pass `DIR_SYZ_SRC=/path/to/syzkaller`.
- Missing `GOBIN`: set it with `go env -w GOBIN=$HOME/.local/bin` and ensure it is on `PATH`.
- Build fails on cache paths under sandboxing: rerun with normal cache access approval; do not redirect caches into the repo unless the user wants that.
- Generated headers/configs collide with old outputs: use `bm-generator/99_clean.sh` carefully; it supports dry-run by default, `-f` to force, and `-a` for deserialized/extracted/build/config cleanup.
- Network traces may need the network-server extraction paths rather than treating all threads as one flat program; inspect `-splitThreads`, TID annotations, accept/connect/bind handling, and unsupported syscall filtering.

