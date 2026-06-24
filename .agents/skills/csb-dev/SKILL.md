---
name: csb-dev
description: "Use when developing or debugging CSB framework internals: bm-runner Python code, configuration parser classes, execution units, monitors, plots, plugins, adapters, Docker/native process orchestration, tests, or framework documentation. For SSH/remote-only behavior, use csb-remote alongside this skill. Use csb for running/adapting benchmark campaigns without changing framework code."
---

# CSB Development

Use this skill for framework implementation work inside CSB. For ordinary benchmark operation and config adaptation, use `csb`. For syzkaller generator internals, use `csb-syzkaller-dev`.

For bugs or validation that depend on a remote benchmark host's kernel, hardware, topology, permissions, containers, perf, bpftrace, or installed runtimes, also use `csb-remote`. Reproduce, test, and validate on the remote CSB checkout; copy logs, test output, configs, and results back to the controller when they are part of the deliverable.

## First Checks

From the CSB root:

```bash
git status --short
sed -n '1,220p' README.md
sed -n '1,260p' doc/bm-runner.md
sed -n '1,260p' doc/bm-config.md
rg --files bm-runner scripts helpers bm-external doc config -g '*.py' -g '*.sh' -g '*.md' -g '*.json'
```

Search framework code, excluding generated/vendor-heavy areas unless needed:

```bash
rg '<term>' bm-runner scripts helpers bm-external doc config bench
```

## Framework Map

- `bm-runner/main.py`: runner entry point and CLI.
- `bm-runner/bm_config.py`: loads JSON and builds config objects.
- `bm-runner/config/`: config model classes, defaults, list expansion, topology/policy settings.
- `bm-runner/benchmark.py`: `ScalabilityBenchmark` benchkit implementation.
- `bm-runner/bm_executer.py`: starts execution units, plugins, monitors, barrier file, cleanup, and output collection.
- `bm-runner/bm_container.py`: privileged Docker container execution.
- `bm-runner/bm_process.py`: native process execution with `taskset`.
- `bm-runner/monitors/`: monitor implementations and factory wiring.
- `bm-runner/bm_visualize.py`: plots and result visualization.
- `scripts/adapters/`: output adapters for external benchmarks.
- `scripts/plugins/`: plugin scripts referenced by JSON configs.

## Development Patterns

Use existing patterns before adding abstractions.

- New config field: add it to the appropriate class under `bm-runner/config/`, update parsing/defaults, update docs, and add tests.
- New execution behavior: start in `ScalabilityBenchmark.single_run()`, then specialize in `bm_container.py`, `bm_process.py`, or `bm_executer.py`.
- New monitor: implement `monitors/monitor.py`, add enum/config wiring, update `monitor_factory.py`, document config, and test failure/empty-output handling.
- New plot type: add `PlotType` and defaults in `config/plot.py`, then implement handling in `bm_visualize.py`.
- New external benchmark adapter: add scripts under `scripts/adapters/` or `scripts/bm-external/`, and ensure output remains `key=value;`.
- New plugin workflow: add scripts under `scripts/plugins/` and reference them in `plugins` JSON.
- CPU/topology changes usually involve `config/container.py`, `config/policy.py`, and `utils/topology.py`.
- Docker/networking changes usually involve `bm_container.py`, `config/nics.py`, and scripts near `scripts/add-nic-to-container.sh`.

Preserve these semantics unless intentionally changing them:

- start-file barrier at `build/bench/start`;
- cleanup of containers, native processes, monitors, plugins, and temporary files;
- semicolon-separated `key=value` output contract;
- result dimensions: `nb_threads`, `noise`, `initial_size`, `container_cnt`, `execution_type`;
- copied config/CSV/HTML sibling artifacts.

## Debugging Workflow

Reproduce with the smallest config: one duration, one repeat, one or two execution-unit counts, and dummy monitors if monitor behavior is not under test.

Useful checks:

```bash
python3 -m json.tool config/<file>.json >/dev/null
scripts/run-single.sh config/<file>.json
cd bm-runner && python3 main.py --replot --title '<title>' --config ../config/<file>.json ../results/<run-dir>
```

When debugging runner behavior:

- inspect copied JSON and CSV beside the result directory;
- inspect per-run stdout/stderr under the run data directory;
- inspect monitor `.err` files and empty outputs;
- keep native and container paths separate until the failing layer is known;
- distinguish benchkit orchestration failures from CSB execution-unit failures.

## Testing Environment

Prepare Python environment with project scripts:

```bash
scripts/prepare.sh
```

For Python changes:

```bash
cd bm-runner
pytest tests
```

Focused tests:

```bash
cd bm-runner
pytest tests/test_env_config.py tests/test_container_config.py tests/test_topology.py
pytest tests/test_with_plugins.py tests/test_perf_monitor.py
```

For config/parser changes, add or adjust tests under `bm-runner/tests/`. For monitor/plugin changes, cover empty files, failed commands, and parsed output. For runner changes touching Docker/perf/sysstat, run unit tests first, then a tiny real benchmark only when host permissions are available.

If Docker, perf, sysstat, cgroups, or NIC setup fail because of host permissions, report the exact requirement and do not paper over it with unrelated code changes.
