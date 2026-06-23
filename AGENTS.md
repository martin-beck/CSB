# AGENTS.md

Project-wide instructions for agents working in this repository.

## Project Shape

CSB is a benchmark framework with three main parts:

- `bm-runner/`: Python runner built on benchkit. It reads JSON configs, builds/runs campaigns, starts execution units, plugins, and monitors, then writes CSV/HTML result artifacts.
- `bench/`: C benchmark harness and benchmark target headers. Builtin benchmarks are headers under `bench/targets/` compiled with `bench/benchmark.c`.
- `bm-generator/` plus `deps/syzkaller/`: experimental strace-to-syzkaller-to-CSB benchmark generation pipeline.

Important supporting directories:

- `config/`: benchmark JSON configs consumed by `bm-runner`.
- `scripts/`: runner scripts, adapters, benchmark plugins, NIC setup, flamegraph-diff tooling, and external benchmark helpers.
- `helpers/`: formatting, test, documentation, and maintenance scripts.
- `doc/`: user and configuration docs. Update these when changing public config or workflows.
- `results/`, `build/`, `Testing/`, generated `config/<group>/`, generated `bench/targets/<group>/`, and `bm-generator/deserialized*` or `bm-generator/extracted*` are usually generated outputs.

Treat `deps/syzkaller` as its own git repository/submodule. Check status and history inside it with `git -C deps/syzkaller ...`; do not mix its changes with the CSB root repo.

## Working Tree Discipline

This checkout often contains generated benchmark headers, configs, result directories, CMake build files, perf outputs, and temporary strace/gdb artifacts. Do not clean, delete, or regenerate them unless the user explicitly asks.

Before changing files, check both repositories:

```bash
git status --short
git -C deps/syzkaller status --short
```

Preserve user changes. If unrelated files are dirty, leave them alone. Avoid destructive commands such as `git reset --hard`, `git checkout --`, or broad `rm` cleanup unless explicitly requested.

## Runner Architecture

The runner entry point is `bm-runner/main.py`. It parses `--config`, builds a `CampaignConfig`, creates a benchkit `CampaignCartesianProduct`, runs the suite, and calls `bm_visualize.visualize_in_html()`.

Key runner files:

- `bm-runner/bm_config.py`: loads JSON and builds config objects.
- `bm-runner/config/`: config model classes for benchmark, application, container, policy, list expansion, NICs, plugins, adapters, plots, and environment overrides.
- `bm-runner/benchmark.py`: `ScalabilityBenchmark`; builds benchmark binaries, saves system/docker info, runs one campaign point, and parses semicolon output.
- `bm-runner/bm_executer.py`: execution-unit lifecycle, plugins, monitors, start barrier, cleanup, and result collection.
- `bm-runner/bm_container.py`: Docker execution.
- `bm-runner/bm_process.py`: native process execution with CPU pinning.
- `bm-runner/monitors/`: monitor implementations and factory.
- `bm-runner/bm_visualize.py`: plot and HTML result generation.

Preserve these runner contracts:

- The start barrier is `build/bench/start` (`ExecutionUnit.START_FILE`).
- Benchmark output is parsed as one line per execution unit with `key=value;` pairs.
- Result dimensions include `nb_threads`, `noise`, `initial_size`, `container_cnt`, and `execution_type`.
- Execution-unit output is prefixed with `execution_unit=<name>;app=<app>;`.
- External benchmark adapters must transform output into the same `key=value;` format.
- Plugins can run at `pre`, `post`, `cleanup`, or `with`; preserve cleanup ordering for containers/processes, monitors, plugins, and the start file.
- `CSB_ANALYZE=false` disables real monitors through `DummyMonitor`; do not special-case monitor disabling elsewhere.
- `CSB_RESULTS_GROUP` redirects results under `results/<group>`.

When adding or changing a config field, update the matching class in `bm-runner/config/`, parsing/defaults, docs under `doc/`, and tests under `bm-runner/tests/`.

## Benchmark Targets

Builtin benchmarks are C headers implementing the interface in `bench/include/CSB/bm_target.h`. They are compiled by `bench/CMakeLists.txt` with `bench/benchmark.c`.

Conventions:

- New manual targets normally go under `bench/targets/`.
- Generated syzkaller headers usually live under grouped target folders and/or `bench/targets/<group>/syz/`.
- `bench/CMakeLists.txt` excludes headers under `syz/` from direct compilation.
- Operation distributions passed via `-opN=` must sum to `1024`.
- Builtin benchmark arguments are `-t`, `-n`, `-d`, `-s`, and `-opN`.
- Generated/minimized targets may compile with `-fno-var-tracking` to keep build time reasonable.

Manual build/test:

```bash
cmake -S. -Bbuild
cmake --build build -j
ctest --test-dir build
```

## Generator And Syzkaller Pipeline

`bm-generator/` stages the benchmark generation pipeline:

1. `00_init.sh`: check/install Go and locate/init syzkaller.
2. `01_build.sh`: build syzkaller tools.
3. `02_parse.sh <strace.log>`: run `syz-trace2syz` and write `.prog` files under `deserialized/`.
4. `03_extract.sh`: minimize/dependency-extract programs into `extracted/`.
5. `04_prepare.sh`: convert extracted `.prog` files to CSB C headers under `bench/targets/<group>/syz/`.
6. `05_generate.sh`: use CMake/tmplr targets to generate wrapper headers and JSON configs.
7. `06_select.sh`: run/select distinct benchmarks using flamegraph differences.

`CSB_RESULTS_GROUP` controls the generator workspace/group name; default is `gen-ws`.

The CSB syzkaller fork extends upstream syzkaller in these areas:

- `tools/syz-trace2syz/`: strace parsing and `.prog` serialization; notable flags include `-deserialize`, `-nocorpus`, `-topCalls`, `-splitThreads`, and `-argLength`.
- `prog/`: serialization/deserialization and CSB-specific annotations such as strace TIDs, return values, clone/resource annotations, and dependency minimization helpers.
- `tools/syz-extraction/`: dependency minimization, poll filtering, deterministic TID iteration, and minimum call count filtering.
- `tools/syz-prog2c/` and `pkg/csource/`: C/CSB header generation, path/socket/file sanitization, FD lifecycle handling, shared buffers, metadata, and CSB config output.
- `executor/` and `sys/linux/sys.txt*`: runtime helpers and syscall descriptions when needed.

Generator scripts intentionally fail on non-empty output directories. Do not bypass that guard without a clear reason.

Build syzkaller tools from the nested repo:

```bash
cd deps/syzkaller
make trace2syz prog2c extraction
```

Focused syzkaller tests:

```bash
cd deps/syzkaller
go test ./tools/syz-trace2syz/parser ./tools/syz-trace2syz/proggen
go test ./prog ./pkg/csource
go test ./tools/syz-extraction ./tools/syz-prog2c ./tools/syz-trace2syz
```

The generator expects Go 1.25 or newer according to the docs/scripts.

## Development Commands

Prepare the Python/benchkit environment:

```bash
scripts/prepare.sh
```

Run Python tests:

```bash
cd bm-runner
pytest tests
```

or from repo root:

```bash
helpers/python-tests.sh
```

Run focused runner tests:

```bash
cd bm-runner
pytest tests/test_env_config.py tests/test_container_config.py tests/test_topology.py
pytest tests/test_with_plugins.py tests/test_perf_monitor.py
```

Run Python checks/formatting:

```bash
helpers/python-checks.sh
```

Validate/format JSON configs:

```bash
helpers/json-format.sh
```

Run a single benchmark config:

```bash
scripts/run-single.sh config/bm_empty.json
```

Replot existing results:

```bash
cd bm-runner
python3 main.py --replot --title '<title>' --config ../config/<file>.json ../results/<run-dir>
```

Some commands require Docker, perf, sysstat, cgroups, NIC privileges, or network access. If they fail because host permissions or services are unavailable, report the exact requirement instead of changing code to hide the failure.

## Remote Host: node26

When the user asks to run anything CSB-related on `node26`, treat `node26` as the benchmark host and this checkout as the instruction/control host.

- Access: use `ssh node26`. The CSB checkout on the remote host is `/home/martin/csb`.
- Skills and agent instructions: read and apply skills from this host checkout, such as `/home/martin/csb/.agents/skills/...`. Do not expect the remote host to contain the active skill state.
- Benchmarks and results: run benchmark commands on `node26` and read/write benchmark configs, generated bundles, monitor outputs, and `results/` artifacts from `/home/martin/csb` on `node26`, unless the user explicitly asks for a local-only operation.
- Kernel source trees on `node26`: `/home/martin/linux-current` and `/home/martin/linux-upstream`. Use those remote trees for source lookup and object-build tests tied to node26 runs.
- BPF/bpftrace templates: local files under `bm-runner/monitors/bpftrace_programs/` in this host checkout are the canonical templates. If a node26 run needs a BPF monitor that is missing or stale remotely, copy or adapt only the needed template to the node26 checkout or a temporary remote config; do not broadly overwrite unrelated remote files.
- Config edits for experiments: preserve remote user changes. Prefer temporary configs under `config/refine/` on `node26` and unique `CSB_RESULTS_GROUP` values for experiments.
- Known node26 setup: Ubuntu Jammy on aarch64, kernel `5.15.0-171-generic`, 128 CPUs, cgroup v2, Docker usable by `martin`, `perf_event_paranoid=-1`, `bpftrace` installed, `libhiredis-dev` installed, `sysstat`/`iostat` installed, and `youki` available at `/usr/local/sbin/youki`.
- Known monitor constraints: `perf_lock`/lock-contention is not useful on the current node26 kernel because lock tracepoints require `CONFIG_LOCKDEP`/`CONFIG_LOCK_STAT`; omit or replace lock plots/monitors for node26 unless a newer kernel proves support. Some PMU events such as `branches` may be unsupported on arm64; keep perf-stat configs tolerant of missing events.
- Arm SPE: for kernel/performance investigations on node26, check whether Arm SPE is available (`perf list` and trace/perf permissions). If available, consider `CSB_ARM_SPE=true` or the matching CSB monitor path for memory-latency/cache evidence.
- Cgroups/youki benchmark setup: before running `config/bm-cgroups-youki.json` or derivatives on node26, ensure `scripts/bm-external/cgroups/prepare.sh` has created `bm-external/cgroups/rootfs` and `config.json`. The helper emits CSB-style `key=value;` output after preparation.
- Remote tool availability can differ from this host. For monitor selection, first check node26 capabilities (`command -v`, `perf list`, tracefs access, `bpftrace --version`, `iostat`) and then choose the closest working monitor set instead of blindly copying local assumptions.

## Common Change Patterns

- New runner config field: update `bm-runner/config/`, config parsing/defaults, `doc/bm-config.md`, and tests.
- New monitor: implement `monitors/monitor.py`, wire `MonitorType` and `MonitorFactory`, document config, and test empty/failing output.
- New plot type: update `config/plot.py` and `bm-runner/bm_visualize.py`.
- New external benchmark: add or update scripts under `scripts/adapters/` or `scripts/bm-external/`, keep adapter output as `key=value;`, and add config/docs.
- CPU/topology behavior: inspect `config/container.py`, `config/policy.py`, and `utils/topology.py`.
- Docker/container behavior: inspect `bm_container.py`, `config/nics.py`, and `scripts/add-nic-to-container.sh`.
- Plugin workflow: add scripts under `scripts/plugins/` and reference them in JSON `plugins`.
- Parser/proggen changes in syzkaller: update Go tests and regenerate parser artifacts if required.
- Extraction changes: test deterministic ordering, dependency preservation, poll filtering, minimum-size filtering, and network split behavior.
- `prog2c`/csource changes: inspect generated headers for sanitized paths, sockets, buffers, FD cleanup/leak handling, metadata, and trace output.

## Style

- Keep edits scoped to the area under change; avoid broad refactors in this prototype codebase.
- Prefer existing helper scripts and local patterns over new tooling.
- Python code uses type hints, straightforward dataclass-like config classes, and `bm_log(..., LogType...)` for user-visible runner messages.
- Shell scripts are Bash and generally use repo-relative paths from the documented working directory. Keep staged generator scripts explicit and easy to debug.
- Preserve license headers when editing existing source files. Add the same MIT/Huawei header to new project source files when consistent with nearby files.
- Use `rg` for searches.
- Do not add generated build/results artifacts to commits unless the user explicitly asks.
