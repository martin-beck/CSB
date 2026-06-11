---
name: csb-syzkaller
description: "Use for operating CSB's syzkaller-based benchmark generation workflow: preparing the bm-generator environment, parsing strace logs, extracting syz programs, generating or refreshing CSB C headers and JSON configs, selecting generated benchmarks, and adapting generated benchmark configs for runs. Do not use for modifying syzkaller internals or generator code; use csb-syzkaller-dev."
---

# CSB Syzkaller Usage

Use this skill to run the CSB `bm-generator/` pipeline and refresh generated benchmark artifacts. Stay on operational workflow, inputs, outputs, and generated config/header adoption. If the task requires changing `deps/syzkaller`, parser/extractor/prog2c code, syzlang internals, Go tests, or generator implementation, use `csb-syzkaller-dev`.

## First Checks

From the CSB root:

```bash
git status --short
git -C deps/syzkaller status --short
sed -n '1,220p' bm-generator/README.md 2>/dev/null || true
rg --files bm-generator config bench/targets deps/syzkaller/bin -g '*.sh' -g '*.json' -g '*.h' -g '*.prog'
```

Inspect existing generated groups:

```bash
find bench/targets -path '*/syz/*.h' | head
find config -name 'bm_min_*.json' | head
```

## Prepare The Generator Environment

Run numbered scripts from `bm-generator/`:

```bash
cd bm-generator
./00_init.sh
./01_build.sh
```

Important variables:

- `DIR_SYZ_SRC`: syzkaller source directory; defaults through `../build/syzkaller-path.txt`.
- `CSB_RESULTS_GROUP`: generated target/config group; defaults to `gen-ws`.
- `JOBS`: parallelism; defaults to `nproc`.
- `MINCALLS`: minimum calls retained during extraction; defaults to `10`.
- `DIR_PROG`: input/output `.prog` directory for parse/extract/prepare steps.
- `DIR_OUT`: extraction output directory.

`00_init.sh` checks Go version. `01_build.sh` builds CSB syzkaller tools through the project build. If Go/tool caches fail because of sandboxing, request normal cache access rather than redirecting caches into the repo.

## Generate From A Trace

Typical pipeline:

```bash
cd bm-generator
./02_parse.sh /path/to/strace.log
./03_extract.sh
./04_prepare.sh
./05_generate.sh
./06_select.sh
```

Pipeline outputs:

- parsed `.prog` files under `bm-generator/deserialized`;
- extracted/minimized `.prog` files under `bm-generator/extracted`;
- generated CSB headers under `bench/targets/<group>/syz`;
- generated JSON configs under `config/<group>`;
- selection/merge outputs from `06_select.sh`.

Script details:

- `02_parse.sh` requires an empty deserialization directory and runs `syz-trace2syz`; it also compares syscall distributions against the trace.
- `03_extract.sh` runs `syz-extraction` for each parsed program and prunes empty outputs.
- `04_prepare.sh` runs `helper/prog2bm.sh`, producing C headers.
- `05_generate.sh` uses CSB templates (`syz_single.h.in`, `bm_single.json.in`) to produce headers/configs.
- `06_select.sh` runs generated configs through flamegraph-based selection and merges selected benchmarks.

## Refresh Headers And Configs After Changes

When generated code/configs are stale after trace, `.prog`, template, or metadata changes:

1. Identify the group:

```bash
export CSB_RESULTS_GROUP=<group>
```

2. Re-run the smallest needed suffix of the pipeline:

- Changed trace parsing input: rerun from `02_parse.sh`.
- Changed extraction settings or selected `.prog`: rerun from `03_extract.sh`.
- Changed `.prog` contents or `prog2bm` output inputs: rerun from `04_prepare.sh`.
- Changed templates or config metadata: rerun `05_generate.sh`.
- Changed selection criteria: rerun `06_select.sh`.

3. Inspect outputs:

```bash
find bm-generator/deserialized bm-generator/extracted -name '*.prog' | head
find bench/targets/"${CSB_RESULTS_GROUP:-gen-ws}"/syz -name '*.h' | head
find config/"${CSB_RESULTS_GROUP:-gen-ws}" -name '*.json' | head
```

4. Validate configs and run with the usage `csb` skill:

```bash
python3 -m json.tool config/"${CSB_RESULTS_GROUP:-gen-ws}"/<file>.json >/dev/null
scripts/run-single.sh config/"${CSB_RESULTS_GROUP:-gen-ws}"/<file>.json
```

## Adapt Generated Configs For Benchmarks

Generated configs can be adjusted for a specific benchmark campaign:

- Keep `applications.name` aligned with the generated header/target name.
- Keep generated `operations` totals valid.
- Adjust `duration`, repeats, `container_list`, execution type, monitors, and plots for the experiment.
- Preserve generator metadata paths used by plugins, especially network-agent metadata for network traces.
- Prefer copying generated configs to a named experiment file instead of editing generated originals when experimenting.

## Common Operational Failures

- `DIR_PROG` not empty during parse: move/clean the output directory before parsing.
- Syzkaller source not found: run `01_build.sh`, configure CSB with `CSB_BM_GENERATOR=ON`, or set `DIR_SYZ_SRC`.
- Missing `GOBIN`: set `go env -w GOBIN=$HOME/.local/bin` and ensure it is on `PATH`.
- Header/config collisions: inspect `bm-generator/99_clean.sh`; it dry-runs by default, `-f` forces cleanup, `-a` includes broad cleanup.
- Network traces may need server/client split-aware extraction; check generated metadata and selected programs before running CSB.
