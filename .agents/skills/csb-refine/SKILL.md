---
name: csb-refine
description: "Use when a CSB benchmark needs an iterative kernel-performance refinement loop: run or rerun CSB, collect perf/monitor evidence, analyze bottlenecks with csb-analysis plus linux-perf and performance-patterns, adapt temporary benchmark configs for runtime, instance counts, native/container mode, monitors, perf/tracefs settings, rerun focused validation points, and produce concise and detailed refined reports."
---

# CSB Refine

Iteratively refine CSB benchmark evidence until each plausible kernel bottleneck from a benchmark is either supported with the best available monitor data or ruled out. This skill coordinates existing skills; it does not replace them.

## Required Skill Coordination

Use these skills in order as needed:

1. `csb`: for config selection/adaptation, temporary run configs, monitor setup, perf/tracefs host prep, and running/replotting CSB.
2. `csb-analysis`: for complete-run detection, per-run reports, cross-run summaries, source correlation, upstream comparison, patch/backport direction, and link checks.
3. `linux-perf`: for perf permission setup, Flow D-style scaling, perf stat/report/annotate/c2c/tracepoint collection, and dual-profile reasoning.
4. `performance-patterns`: for deciding which named patterns match or do not match, and for reading the relevant pattern detail files before suggesting fixes.

If `linux-perf` or `performance-patterns` is not available but `deps/intel-performance-skills/skills/<skill>/SKILL.md` exists, read the local skill files. If the local tree is missing and network access is approved, clone `https://github.com/intel/intel-performance-skills.git` into `deps/intel-performance-skills`.

## Refinement Loop

For each requested benchmark or initial config:

1. **Baseline run or locate existing run**
   - If a complete result already exists, start from it.
   - Otherwise run CSB using `csb`, with normal result siblings `<run>/`, `<run>.json`, `<run>.html`, and `<run>.csv`.
   - Before perf-backed runs, try to set `perf_event_paranoid=-1` and check/remount tracefs as described in `csb`/`csb-analysis`. If blocked, record the exact limitation.

2. **First analysis**
   - Run `csb-analysis` on the complete result.
   - Extract every plausible kernel bottleneck hypothesis from the report: subsystem, benchmark dimensions, inflection point, hot symbols, monitor gaps, linux-perf classification, performance-pattern match/non-match, confidence, and missing evidence.
   - Keep hypotheses separate. Do not merge native/container or different instance/thread/noise/initial-size dimensions unless the evidence supports it.

3. **Design a temporary focused config**
   - Copy the original config to a temporary refinement config under a clearly named scratch path such as `config/refine/` or a user-specified group. Do not overwrite the original config.
   - Adapt only parameters needed to gather new evidence:
     - `duration`: long enough for stable perf/monitor data, short enough for iteration.
     - `container_list` / instance counts: include baseline, peak/plateau, first cliff, largest count, and adjacent-drop points.
     - `execution_type`: include native and/or container only when relevant to the hypothesis.
     - `threads`, `noise`, `initial_size`, CPU pinning, and cgroup/container settings: keep constant unless the hypothesis requires varying them.
     - monitors: enable only those that answer the hypothesis.
   - Prefer focused reruns over broad sweeps once an inflection is known.

4. **Monitor selection by hypothesis**
   - fsync/writeback/block: perf call graphs, `mpstat`, `iostat`, block tracepoints, flush/writeback/journal tracepoints or bpftrace if available.
   - VFS path/dentry/inode: perf call graphs, syscall tracepoints, source-resolvable kernel symbols, optional LSM/fsnotify/refcount tracepoints when suspected.
   - read/write iterator/copy: perf report/annotate, hardware counters, syscall tracepoints, copy/uaccess/filemap/ext4 symbols.
   - lock/cache-line: perf-lock or lock-contention, `perf c2c`, perf annotate of lock/cmpxchg sites, HITM/offset evidence.
   - scheduler/wakeup/futex: context switches, sched tracepoints, futex/syscall tracepoints, perf sched if available.
   - network/socket/TCP: socket/syscall tracepoints, softirq/mpstat, perf call graphs, skb/tcp symbols.
   - memory-management/page-cache: page faults, filemap, reclaim/writeback tracepoints, perf call graphs and counters.

5. **Rerun and re-analyze**
   - Run the temporary config.
   - Generate fresh per-run and cross-run analysis.
   - Compare new evidence against the previous hypothesis:
     - confirmed: benchmark inflection, monitor signal, source path, and pattern classification align;
     - weakened: new evidence points elsewhere or removes the suspected signal;
     - blocked: permission/tooling prevents required evidence collection;
     - split: multiple bottlenecks are visible and need separate focused configs.

6. **Iterate**
   - For each confirmed or still-plausible hypothesis, refine the config again to close the largest remaining evidence gap.
   - Stop iterating on a hypothesis when one of these is true:
     - the required evidence has been collected for benchmark behavior, monitor signal, source path, and pattern classification;
     - the hypothesis is contradicted by focused reruns;
     - remaining evidence requires unavailable host permissions/hardware/tooling;
     - additional reruns would repeat the same evidence without changing confidence;
     - the user-specified time/run budget is exhausted.

7. **Continue across hypotheses**
   - Process every plausible kernel bottleneck extracted from the benchmark.
   - If fixing or validating one hypothesis exposes a new bottleneck in later reruns, add it to the queue and mark its source run.

## Temporary Config Discipline

- Keep temporary configs obviously temporary and link them from reports.
- Preserve original configs and generated headers unless the user explicitly asks to edit them.
- Keep runtime and monitor overhead proportional to the question. For heavy monitors such as c2c, tracepoints, bpftrace, or perf sched, run only the counts needed for validation.
- Record host state in each refinement report: perf paranoia, tracefs status, monitor availability, sudo limitations, kernel/source tree commits, and any dirty source trees used for correlation.

## Evidence Rules

- A severe scaling drop is not enough. Require benchmark inflection plus a matching monitor signal plus plausible kernel source path before raising confidence.
- A named `performance-patterns` fix requires the specific evidence demanded by that pattern file. For example, false sharing needs c2c HITM/offset proof; per-CPU stats needs true-sharing counter proof; TTAS needs lock/CAS evidence; mutex-to-rwlock needs lock evidence and read-mostly source semantics.
- If the bottleneck is device flush latency, scheduler sleep, external serialization, or missing permission rather than CPU/cache-line contention, say so and avoid forcing a pattern.
- Keep negative evidence: explicitly list tempting patterns that were ruled out and why.

## Reports

At the end, write both reports under the refinement result directory or another user-specified location:

- `refine-summary.md/html`: concise executive summary with final hypotheses, status, confidence, best evidence, rejected hypotheses, recommended next actions, and links.
- `refine-detailed.md/html`: full iteration log with configs, commands, run IDs, parameter changes, monitor data, linux-perf/performance-patterns interpretation, source/upstream correlation, validation gaps, and patch/backport implications.

Reports must link:

- original and temporary configs;
- every complete result HTML/CSV/report used;
- generated per-run and cross-run analysis HTML;
- relevant `deps/linux` and `deps/linux-upstream` source paths;
- perf/monitor artifacts when practical.

Before finishing, render Markdown to HTML and run local Markdown link checks. Missing artifacts must be written as `missing`, not linked.

