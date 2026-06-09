---
name: csb
description: "Use when working in the CSB Container Scalability Benchmarks repository: configuring JSON benchmark campaigns, running or replotting bm-runner benchmarks, interpreting CSB result artifacts, adding external benchmark adapters/plugins/monitors/plots, or modifying the Python framework. Do not use this skill for deps/syzkaller internals; syzkaller-based generation is handled by a separate skill."
---

# CSB

CSB is the Container Scalability Benchmarks suite. It runs builtin C microbenchmarks and external workloads under different concurrency configurations, especially threads, native processes, and containers, then records CSV measurements and plots for scalability and system-behavior analysis.

## Boundaries

- Focus on CSB project code: `bm-runner/`, `config/`, `bench/`, `scripts/`, `helpers/`, docs, and examples.
- Treat `deps/benchkit` as an embedded dependency that provides campaign orchestration, shell helpers, and chart/dataframe support.
- Do not read or modify `deps/syzkaller` for this skill. If a task needs syzkaller internals or benchmark generation details, use the separate csb-syzkaller skill.

## First Checks

Start from the project root. Prefer these reads before changing code:

```bash
sed -n '1,220p' README.md
sed -n '1,260p' doc/bm-runner.md
sed -n '1,260p' doc/bm-config.md
rg --files bm-runner config scripts helpers bm-external doc -g '*.py' -g '*.json' -g '*.md' -g '*.sh'
```

For code search, exclude generated/vendor-heavy areas unless needed:

```bash
rg '<term>' bm-runner config scripts helpers bm-external doc bench
```

## Execution Model

The main runner is `bm-runner/main.py`.

- `CampaignConfig` in `bm-runner/bm_config.py` loads the JSON file and builds config objects.
- `csbCampaign()` creates a `benchkit.campaign.CampaignCartesianProduct` over `nb_threads`, `noise`, `initial_size`, `container_cnt`, and `execution_type`.
- `ScalabilityBenchmark` in `bm-runner/benchmark.py` is the benchkit benchmark implementation.
- `ScalabilityBenchmark.single_run()` assigns applications round-robin across execution units and chooses `Containers` or `Processes`.
- `Executer` in `bm-runner/bm_executer.py` starts execution units, runs plugins, starts monitors, touches `build/bench/start` as the synchronized start signal, waits, cleans up, and collects output.
- `parse_output_to_results()` expects each execution unit output as semicolon-separated `key=value` pairs and adds common fields like kernel, allowed CPUs, and cgroup version.

Container execution:

- `bm-runner/bm_container.py` creates privileged Docker containers.
- The CSB project is mounted inside each container as `/home`.
- CPU placement uses Docker `cpuset_cpus`.
- Optional NIC/VF setup is driven by `nics` config and `scripts/add-nic-to-container.sh`.

Native execution:

- `bm-runner/bm_process.py` starts host processes with `taskset --cpu-list`.
- It uses the same start-file synchronization and output-file contract as containers.

## Configuring Runs

The primary control surface is a JSON file under `config/`, documented in `doc/bm-config.md`.

Core top-level keys:

- `applications`: required list of builtin or external applications.
- `benchmark_config`: duration, repeat count, thread list, noise, initial sizes, execution environments, and monitors.
- `containers`: container/native execution-unit count and CPU assignment policy.
- `plugins`: scripts run at `pre`, `post`, `cleanup`, or `with` execution times.
- `plots`: generated plots from result CSV columns.
- `nics`: optional NIC/VF assignment for container networking benchmarks.

List expansion uses `bm-runner/config/list.py`:

```json
{ "values": [[1], {"min": 2, "max": 16, "step": 2}] }
```

Use `container_list` for number of execution units and `benchmark_config.threads` for threads per execution unit. If `container_list` is omitted, CSB computes a range from detected CPU topology and `core_count`.

Important application details:

- Builtin apps default to `build/bench/<name>`.
- External apps use `path` relative to the CSB root. In containers, that root is mounted as `/home`.
- `args` supports placeholders: `{threads}`, `{noise}`, `{duration}`, `{index}`, `{initial_size}`, `{n_units}`, `{homedir}`, `{res_dir}`, and `{host_ip}`.
- Builtin benchmark `operations` values must sum to `1024`.
- External benchmark adapters must emit `key=value;` pairs.

Common environment toggles:

- `CSB_RESULTS_GROUP=<name>` writes under `results/<name>`.
- `CSB_ANALYZE=false` disables real monitors via dummy monitors.
- `CSB_NO_BUILD_BENCH=true` skips builtin benchmark builds.
- `CSB_NO_CLEAN_BENCH=true` keeps previous builtin build artifacts.
- `CSB_PIN_MONITORS=true` pins monitors to the last CPU.
- `CSB_ARM_SPE=true` enables Arm SPE perf capture when available.

## Running And Replotting

Normal interactive run:

```bash
./run.sh
```

Direct runner invocation:

```bash
cd bm-runner
python3 main.py --title '<title>' --config ../config/<file>.json
```

Single-config wrapper, useful from scripts because it prepares the venv and common CSB paths first:

```bash
scripts/run-single.sh config/<file>.json [extra main.py args]
```

`scripts/run-single.sh` runs from the CSB root, resolves the config path, derives the title from the JSON filename, exports `FLAMEGRAPH`, `SHE_HULK_ADAPTERS`, `CSB_ADAPTERS`, and `CSB_PLUGINS`, sets `CSB_NO_BUILD_BENCH=ON`, runs `scripts/prepare.sh`, activates `./venv`, raises the open-file limit to the hard limit, then invokes `bm-runner/main.py --title <config-basename> --config <absolute-config>`.

Replot an existing result directory without rerunning workloads:

```bash
cd bm-runner
python3 main.py --replot --title '<title>' --config ../config/<file>.json ../results/<run-dir>
```

Bulk/generated configs can be run with:

```bash
scripts/run-all.sh '<pattern>'
```

Result artifacts usually include:

- a benchkit CSV next to the run directory;
- a copied JSON config beside the CSV;
- `results.html` with embedded plots and monitor artifacts;
- per-run output/error files under `build/bench`;
- monitor outputs under the run data directory.

For cross-run analysis, use:

```bash
cd bm-runner
python3 analyze.py ../results/<dir1> ../results/<dir2>
```

## Modifying The Framework

Use existing patterns before adding abstractions:

- New config field: add it to the appropriate class under `bm-runner/config/`, update parsing/defaults, update `doc/bm-config.md`, and add or adjust tests under `bm-runner/tests/`.
- New execution behavior: start in `ScalabilityBenchmark.single_run()`, then specialize in `bm_container.py`, `bm_process.py`, or `bm_executer.py`.
- New monitor: implement `monitors/monitor.py`, add its enum value in `config/benchmark.py`, wire it in `monitors/monitor_factory.py`, and document monitor config.
- New plot type: add `PlotType` and defaults in `config/plot.py`, then implement handling in `bm_visualize.py`.
- New external benchmark: add a config under `config/`, an adapter under `scripts/adapters/` if output is not already `key=value;`, and optional setup scripts under `scripts/bm-external/`.
- New plugin workflow: add scripts under `scripts/plugins/` and reference them in the `plugins` JSON section.
- CPU/topology changes usually involve `config/container.py`, `config/policy.py`, and `utils/topology.py`.
- Docker/networking changes usually involve `bm_container.py`, `config/nics.py`, and scripts near `scripts/add-nic-to-container.sh`.

Be careful with benchmark semantics:

- Preserve the start-file barrier unless intentionally changing synchronization.
- Preserve cleanup paths for containers, native processes, monitors, and plugins.
- Keep output parseable as semicolon-separated `key=value` fields.
- Avoid changing default CPU selection or monitor behavior without updating docs and tests.

## Validation

For Python changes, run focused tests first:

```bash
cd bm-runner
pytest tests
```

Useful focused tests:

```bash
cd bm-runner
pytest tests/test_env_config.py tests/test_container_config.py tests/test_topology.py
pytest tests/test_with_plugins.py tests/test_perf_monitor.py
```

For config-only changes, validate JSON and do a dry inspection of parsed config paths. For real benchmark execution, prefer a small config such as `bm_empty.json` with short duration and one repeat before scaling up.

Running full benchmarks may require Docker access, `perf`, `sysstat`, sudo-able NIC operations, and host-level permissions. If a command fails because of Docker, perf, or network access, report the exact requirement rather than masking it with code changes.
