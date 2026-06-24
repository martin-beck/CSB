---
name: csb
description: "Use for operating the CSB Container Scalability Benchmarks framework: preparing the runtime environment, choosing JSON configs for a target application, running bm-runner campaigns, configuring linux-perf-friendly monitors, replotting existing results for ordinary benchmark runs."
---

# CSB Usage

Use this skill to run CSB benchmark campaigns. Stay on the user-facing surfaces: `config/`, `scripts/`, `bench/targets/`, `results/`, `doc/`, and runner commands. If the task requires editing `bm-runner/` framework code, adding monitors/plugins/framework behavior, or debugging internals, switch to `csb-dev`.

## First Checks

Start at the CSB root:

```bash
pwd
sed -n '1,220p' README.md
sed -n '1,260p' doc/bm-runner.md
sed -n '1,260p' doc/bm-config.md
rg --files config scripts bench/targets doc -g '*.json' -g '*.sh' -g '*.md' -g '*.h'
```

Before editing configs, inspect nearby examples and the active config:

```bash
sed -n '1,220p' config/<group>/<file>.json
rg '"benchmark_config"|"applications"|"containers"|"plugins"|"plots"' config/<group>
```

## Prepare The Runtime Environment

Use existing scripts rather than hand-rolling setup:

```bash
scripts/prepare.sh
```

For one benchmark config, prefer:

```bash
scripts/run-single.sh config/<file>.json [extra main.py args]
```

Useful environment toggles can be found in `doc/bm-config.md#environment-variables`.

Running full benchmarks may require Docker access, `perf`, `sysstat`, sudo-able NIC operations, and host permissions. If these fail, report the exact missing capability.

## Configure A Specific Application

Primary config surface: JSON under `config/`, documented in `doc/bm-config.md`. Refer to this document for any further application specific configuration.

## Run, Replot, And Inspect

Normal interactive run:

```bash
./run.sh
```

Direct runner:

```bash
scripts/run-single.sh config/<file>.json [extra main.py args]
```

Replot without rerunning workloads:

```bash
cd bm-runner
python3 main.py --replot --title '<title>' --config ../config/<file>.json ../results/<run-dir>
```

Bulk configs:

```bash
scripts/run-all.sh '<pattern>'
```

Expected complete result siblings:

- `results/<run>/`
- `results/<run>.json`
- `results/<run>.html`
- `results/<run>.csv`

Per-run monitor files usually live below:

`nb_threads-*/noise-*/initial_size-*/container_cnt-*/execution_type-*/run-*/`

For post-run performance analysis, use `csb-analysis`.

## linux-perf-Friendly Runs

When the user's goal is kernel performance analysis, scaling diagnosis, or later patch selection, configure the run so `csb-analysis` can apply `linux-perf` and `performance-patterns` evidence cleanly.

Whenever perf data would materially improve the run or later analysis, try to enable full perf visibility before running the benchmark:

```bash
cat /proc/sys/kernel/perf_event_paranoid
echo -1 | sudo tee /proc/sys/kernel/perf_event_paranoid
cat /proc/sys/kernel/perf_event_paranoid
```

For perf tracepoints, bpftrace, scheduler/block events, and other trace-based monitors, also check tracefs. Prefer `/sys/kernel/tracing`; fall back to `/sys/kernel/debug/tracing` only when needed:

```bash
TRACEFS=/sys/kernel/tracing
test -d "$TRACEFS" || TRACEFS=/sys/kernel/debug/tracing
findmnt -T "$TRACEFS"
test -r "$TRACEFS/events" && test -x "$TRACEFS/events"
sudo mount -o remount,mode=755 "$TRACEFS"
test -r "$TRACEFS/events" && test -x "$TRACEFS/events"
```

If tracefs is not mounted, try mounting it before the remount:

```bash
sudo mount -t tracefs nodev /sys/kernel/tracing
```

If sudo is denied, unavailable, or policy blocks the change, continue with the best available monitors and record that perf or tracefs collection was permission-limited. Do not silently downgrade to weaker evidence. After enabling perf and tracefs access, run a useful small benchmark point that can verify the hypothesis, usually baseline count, peak/plateau count, and cliff or largest count with the relevant perf monitor enabled.

Before running, check whether `linux-perf` is available as a skill or local reference under `deps/intel-performance-skills/skills/linux-perf`. If it is missing and network access is permitted or approved, clone the skill bundle:

```bash
git clone https://github.com/intel/intel-performance-skills.git deps/intel-performance-skills
```

Use the linux-perf setup guidance to decide which monitors are worth enabling. Prefer the smallest monitor set that answers the question:

- CPU/syscall hot path: enable CSB `perf` and `mpstat`.
- Lock contention: enable `perf_lock` monitor if available.
- Cache-line contention or false sharing: collect `perf c2c` evidence when host permissions and hardware support allow it.
- I/O or fsync/writeback cliffs: enable `mpstat`, `iostat` if available, and a block/flush bpftrace or perf tracepoint monitor if the config supports it.
- Scheduler/wakeup cliffs: collect context-switch, sched latency, futex/wakeup, or scheduler tracepoint evidence when available.

For scaling sweeps intended for linux-perf Flow D-style analysis, include at least:

- a baseline count;
- the expected peak or plateau count;
- the first cliff/regression count;
- the largest count;
- both native and container execution types when the question includes container overhead.

If host permissions prevent perf, c2c, lock, or bpftrace monitors, do not hide the failure by disabling analysis silently. Record the missing permission in the result notes or final response so `csb-analysis` can distinguish "no evidence" from "no bottleneck."

When a hypothesis already exists, prefer a targeted perf-backed confirmation run over another broad sweep. Examples:

- fsync/writeback hypothesis: run the fsync-heavy benchmark at the baseline and cliff counts with perf plus `iostat`/block evidence.
- VFS path hypothesis: run the path-heavy benchmark with perf call graphs and source-resolvable kernel symbols.
- lock/cache-line hypothesis: run the contention point with perf-lock or `perf c2c` if supported.
- scheduler/wakeup hypothesis: run the cliff point with context-switch and sched/futex trace evidence.

Before relying on tracepoint events, verify that they are visible to `perf`, for example:

```bash
perf list 'block:*' 'sched:*' 'syscalls:*' >/tmp/csb-perf-tracepoint-list.txt
```

If the list is empty or perf reports tracefs permission errors, fix tracefs permissions or document the limitation in the run notes.

