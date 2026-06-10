---
name: csb-syzkaller-dev
description: "Use when developing or debugging CSB's deps/syzkaller fork or bm-generator internals: trace parsing, syzlang serialization/extraction, prog2c CSB header generation, generated benchmark metadata, Go tooling/tests, or generator templates. Use csb-syzkaller for operating the generation pipeline without changing internals."
---

# CSB Syzkaller Development

Use this skill for implementation work in `deps/syzkaller` and CSB `bm-generator/`. For running the generator pipeline or refreshing generated headers/configs without changing internals, use `csb-syzkaller`.

## First Checks

From the CSB root:

```bash
git status --short
git -C deps/syzkaller status --short
git -C deps/syzkaller log --oneline --decorate --max-count=50
rg --files bm-generator deps/syzkaller/tools/syz-trace2syz deps/syzkaller/tools/syz-extraction deps/syzkaller/tools/syz-prog2c deps/syzkaller/prog deps/syzkaller/pkg/csource deps/syzkaller/executor
```

Focused search:

```bash
rg '<term>' bm-generator deps/syzkaller/tools/syz-trace2syz deps/syzkaller/tools/syz-extraction deps/syzkaller/tools/syz-prog2c deps/syzkaller/prog deps/syzkaller/pkg/csource
```

Treat `deps/syzkaller` as its own git repository/submodule. Do not mix its status/history with the CSB root.

## Internal Architecture

The CSB fork turns captured executions into CSB microbenchmarks:

1. parse `strace` logs into syzlang programs;
2. preserve strace TIDs and syscall return values in `.prog` serialization;
3. extract smaller syscall programs representing kernel task slices;
4. sanitize paths, descriptors, sockets, buffers, and unsupported calls;
5. convert syzlang programs into CSB C headers;
6. generate JSON configs for CSB.

Core areas:

- `tools/syz-trace2syz/`: strace lexer/parser/proggen; `-deserialize`, `-nocorpus`, `-topCalls`, `-splitThreads`, `-argLength`.
- `prog/`: serialization of `<tid>`, `[ret]`, cloning annotations, dependency annotations, minimization.
- `tools/syz-extraction/`: dependency minimization, poll filtering, minimum call count, deterministic TID iteration, network-server split handling.
- `tools/syz-prog2c/` and `pkg/csource/`: `-csb`, syscall tracing, path/socket/file sanitization, FD leak handling, shared write/send buffers, metadata, CSB config output.
- `executor/common*.h` and `sys/linux/sys.txt*`: runtime helpers and syscall descriptions.
- `bm-generator/`: numbered pipeline scripts, templates, helper scripts, selection/cleanup.
- `Makefile`: CSB tool targets `trace2syz`, `prog2c`, and `extraction`.

## Development Patterns

- Parser syntax changes: update parser/proggen tests and regenerate parser artifacts when required:

```bash
cd deps/syzkaller
make generate_trace2syz
```

- Extraction changes: test dependency preservation, deterministic ordering, minimum-size behavior, network split handling, and empty-output pruning.
- Prog serialization changes: check round-trip compatibility and expected `<tid>` / `[ret]` annotations.
- `prog2c`/csource changes: inspect generated C headers for sanitized paths, stable buffers, FD cleanup/leak handling, metadata, and trace output.
- Template/config changes: rerun `bm-generator/05_generate.sh` and validate generated JSON plus header names.
- Network trace changes: inspect bind/connect/accept rewriting, server/client thread separation, unsupported syscall filtering, and network-agent metadata.

Avoid deleting generated outputs unless the user asked for cleanup/regeneration. Generated artifacts are often untracked.

## Build And Test Environment

Prepare generator environment:

```bash
cd bm-generator
./00_init.sh
./01_build.sh
```

Build tools directly:

```bash
cd deps/syzkaller
make trace2syz prog2c extraction
```

Focused Go tests:

```bash
cd deps/syzkaller
go test ./tools/syz-trace2syz/parser ./tools/syz-trace2syz/proggen
go test ./prog ./pkg/csource
go test ./tools/syz-extraction ./tools/syz-prog2c ./tools/syz-trace2syz
```

Full tests:

```bash
cd deps/syzkaller
make test
```

Environment notes:

- The CSB workflow expects Go 1.25 or newer; `00_init.sh` checks this.
- Syzkaller's Makefile sets `GOBIN` to `deps/syzkaller/bin` while building tools.
- Plain `go test` uses normal `GOCACHE`, `GOMODCACHE`, and compiler caches; sandboxed environments may need approval for home/cache access.
- Syzkaller may warn that `tools/syz-env` is preferred for upstream compatibility; report it, but it is not a failure by itself.
- Some upstream tests may be stale against CSB-specific `[ret]` annotations or signature changes. Treat as test-suite drift unless the user asks to repair tests.

## Debugging Generated Benchmarks

For a failing generated benchmark:

```bash
find bm-generator/deserialized bm-generator/extracted -name '*.prog' | head
find bench/targets/"${CSB_RESULTS_GROUP:-gen-ws}"/syz -name '*.h' | head
find config/"${CSB_RESULTS_GROUP:-gen-ws}" -name '*.json' | head
```

Trace the failure stage:

- parse mismatch: compare strace syscall distribution to `.prog` output;
- extraction mismatch: inspect dependencies, TIDs, returns, and min-call filtering;
- header build/runtime failure: inspect generated `.h`, sanitizer output, buffers, and FD lifecycle;
- CSB run failure: hand off to `csb` or `csb-dev` depending on whether config usage or runner internals are failing.

Common internal failure modes:

- stale generated parser after syntax changes;
- nondeterministic TID/program ordering;
- unsupported syscall not filtered or sanitized;
- path/socket rewrite invalid for replay;
- FD leak cleanup removing a needed descriptor;
- generated config/header names diverging from target names;
- tests expecting upstream serialization rather than CSB annotations.
