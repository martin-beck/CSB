---
name: csb-refine
description: "Use when a CSB benchmark needs an iterative kernel-performance refinement loop: run or rerun CSB, collect perf/monitor evidence, analyze bottlenecks with csb-analysis plus linux-perf and performance-patterns, adapt temporary benchmark configs for runtime, instance counts, native/container mode, monitors, perf/tracefs settings, rerun focused validation points, create and object-build-test an RFC-style kernel patch for the most likely optimization, and produce concise and detailed refined reports."
---

# CSB Refine

Iteratively refine CSB benchmark evidence until each plausible kernel bottleneck from a benchmark is either supported with the best available monitor data or ruled out, then draft and object-build-test a likely kernel optimization patch in RFC style. This skill coordinates existing skills; it does not replace them.

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
   - For each hypothesis, state the exact evidence gap that prevents a sharper conclusion. Prefer gaps that can be closed by changing the CSB configuration or monitor set, such as missing cliff-adjacent counts, too-short runtime, missing lock/HITM/tracepoint data, mixed native/container effects, missing CPU isolation, or monitor overhead hiding the signal.
   - Keep hypotheses separate. Do not merge native/container or different instance/thread/noise/initial-size dimensions unless the evidence supports it.

3. **Design a temporary focused config and expected signal**
   - Copy the original config to a temporary refinement config under a clearly named scratch path such as `config/refine/` or a user-specified group. Do not overwrite the original config.
   - Treat configuration adaptation as a primary output of the refinement, not a mechanical rerun. Before running, write a short adaptation plan for each hypothesis with:
     - hypothesis being tested;
     - configuration fields to change;
     - monitors to add, remove, or reconfigure;
     - why each change should sharpen the signal;
     - expected monitor movement if the hypothesis is true;
     - expected negative evidence if the hypothesis is false;
     - overhead or confounding risk introduced by the monitor/change.
   - Adapt only parameters needed to gather new evidence:
     - `duration`: long enough for stable perf/monitor data, short enough for iteration.
     - `container_list` / instance counts: include baseline, peak/plateau, first cliff, largest count, and adjacent-drop points.
     - `execution_type`: include native and/or container only when relevant to the hypothesis.
     - `threads`, `noise`, `initial_size`, CPU pinning, and cgroup/container settings: keep constant unless the hypothesis requires varying them.
     - monitors: enable only those that answer the hypothesis; remove broad or expensive monitors when they obscure the targeted signal.
   - When the first run is too broad or noisy, narrow the next config so the result clearly separates "hypothesis true" from "hypothesis false". Examples: use only baseline/peak/cliff counts for `perf c2c`; only cliff points for scheduler tracepoints; adjacent counts around a throughput cliff for lock contention; native-vs-container paired points when runtime overhead is suspected.
   - Prefer focused reruns over broad sweeps once an inflection is known.

4. **Monitor selection by hypothesis**
   - fsync/writeback/block: perf call graphs, `mpstat`, `iostat`, block tracepoints, flush/writeback/journal tracepoints or bpftrace if available.
   - VFS path/dentry/inode: perf call graphs, syscall tracepoints, source-resolvable kernel symbols, optional LSM/fsnotify/refcount tracepoints when suspected.
   - read/write iterator/copy: perf report/annotate, hardware counters, syscall tracepoints, copy/uaccess/filemap/ext4 symbols.
   - lock/cache-line: perf-lock or lock-contention, `perf c2c`, perf annotate of lock/cmpxchg sites, HITM/offset evidence.
   - scheduler/wakeup/futex: context switches, sched tracepoints, futex/syscall tracepoints, perf sched if available.
   - network/socket/TCP: socket/syscall tracepoints, softirq/mpstat, perf call graphs, skb/tcp symbols.
   - memory-management/page-cache: page faults, filemap, reclaim/writeback tracepoints, perf call graphs and counters.
   - cgroup lifecycle/task migration: perf call graphs, lock contention, `cgroup:*` tracepoints when present, sched/process tracepoints, focused probes or bpftrace around `cgroup_mkdir`, `__cgroup_procs_write`, `cgroup_rmdir`, `kernfs_*`, and RCU expedited paths.
   - cgroup rstat/accounting: `cgroup_rstat_flush`/`cgroup_rstat_lock` evidence via perf, lock contention, tracepoints or kprobes, plus stats-reader workload dimensions that vary tree breadth/depth and dirtying rate.
   - controller-specific cgroup limits: pair controller counters with syscall/scheduler evidence. For memory use `memory.events`, reclaim/fault data, and memcg symbols; for pids use fork/clone/sched/process counters and pids events.

5. **Rerun and re-analyze**
   - Run the temporary config.
   - Generate fresh per-run and cross-run analysis.
   - Compare new evidence against the previous hypothesis:
     - confirmed: benchmark inflection, monitor signal, source path, and pattern classification align;
     - weakened: new evidence points elsewhere or removes the suspected signal;
     - blocked: permission/tooling prevents required evidence collection;
     - split: multiple bottlenecks are visible and need separate focused configs.
   - If the new evidence is still too diffuse, do not just repeat the same run. Propose the next sharper config/monitor change or explain why no CSB-accessible configuration can isolate the bottleneck further.

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

8. **Create an RFC kernel patch after successful refinement**
   - After at least one kernel bottleneck is confirmed or strongly supported, create a compilable Linux kernel patch that would most likely improve the measured performance. Treat this as part of a successful refine result, not an optional follow-up.
   - Use the source tree identified by the analysis, preferring the benchmarked tree such as `deps/linux` when present. If a separate upstream comparison tree such as `deps/linux-upstream` was used, cite it for provenance but patch the intended target tree.
   - Keep the patch conservative and evidence-linked. Optimize the smallest kernel path that matches the refined evidence; avoid broad subsystem rewrites, speculative algorithm swaps, or pattern fixes that were not supported by monitor data.
   - Write the patch in typical Linux RFC style:
     - subject starts with `[RFC PATCH]`;
     - commit message explains the benchmark symptom, refined monitor evidence, affected kernel path, intended optimization, safety/correctness reasoning, and validation status;
     - include `Not-yet-signed-off-by:` or a clear placeholder only if the user has not supplied authorship/signoff instructions;
     - add comments sparingly and only where kernel reviewers would need them.
   - Place patch outputs in a clearly named result directory, for example `patch-series-<hypothesis>/0001-rfc-<subsystem>-<short-topic>.patch`, and link them from both reports.
   - If the best patch direction is a backport of an existing upstream commit, create the backport-style patch against the target tree and cite the upstream commit in the commit message. If a direct backport does not apply, produce the minimal adapted RFC patch and explain the adaptation.
   - If no responsible patch can be produced from the evidence, write a `patch-deferred.md` support document instead of inventing code. It must name the missing evidence or unsafe semantic ambiguity and the exact additional monitor/source inspection needed.

9. **Apply and object-build-test the patch temporarily**
   - Temporarily apply the RFC patch to the target kernel tree, preserving unrelated user changes. Prefer `git apply --check` first, then apply the patch.
   - Compile the affected object or narrow subsystem target rather than a full kernel unless the user requested a full build. Examples: `make M=<subdir> <file>.o`, `make kernel/cgroup/cgroup.o`, or the closest valid target for the edited file.
   - If the object build fails, fix the patch and retest when the failure is patch-related. If the failure is environmental or pre-existing, record the exact command and error.
   - After the compile test, leave the workspace in a clear state:
     - either keep the patch applied only when the user asked for an applied tree or the workflow needs it for immediate validation;
     - otherwise reverse only the patch changes you made, leaving unrelated dirty files untouched, and keep the patch file as the deliverable.
   - Record the apply command, build command, build result, and tree state in the detailed report.

10. **Patch support documents**
   - Alongside the patch, write concise support documentation for reviewer and user context:
     - `patch-rationale.md`: evidence-to-code mapping, why this patch is the most likely performance improvement, expected benchmark/monitor movement, and follow-up validation run.
     - `patch-safety.md`: locking/lifetime/RCU/refcount/memory-ordering/API compatibility analysis, why correctness should be preserved, and what risks remain.
   - When the patch changes synchronization, explicitly discuss deadlock ordering, lifetime ownership, concurrent create/remove/attach cases, and fallback behavior.
   - When the patch changes accounting, batching, deferral, or caching, explicitly discuss visibility semantics, error paths, teardown, and rollback behavior.

## Temporary Config Discipline

- Keep temporary configs obviously temporary and link them from reports.
- Preserve original configs and generated headers unless the user explicitly asks to edit them.
- Keep runtime and monitor overhead proportional to the question. For heavy monitors such as c2c, tracepoints, bpftrace, or perf sched, run only the counts needed for validation.
- Prefer signal clarity over config breadth. A good refinement config should make the suspected kernel cause visible in at least one captured monitor artifact, or produce strong negative evidence that the cause is absent.
- Do not leave adaptation implicit. Every temporary config must have a recorded rationale for changed duration, instance counts, execution type, threads, CPU pinning, controller settings, monitor list, and monitor-specific options.
- Record rejected adaptations too, especially monitors that would be ideal but are unavailable due to kernel config, tracefs/perf permission, hardware support, excessive overhead, or missing CSB monitor plumbing.
- Record host state in each refinement report: perf paranoia, tracefs status, monitor availability, sudo limitations, kernel/source tree commits, and any dirty source trees used for correlation.

## Evidence Rules

- A severe scaling drop is not enough. Require benchmark inflection plus a matching monitor signal plus plausible kernel source path before raising confidence.
- A patch proposal is not justified by benchmark shape alone. It must cite the refined monitor signal and kernel source path it is intended to improve.
- A refinement is incomplete if it only reports "reran with more monitors" without explaining which configuration changes made the hypothesis easier to prove or disprove.
- Prefer monitor evidence that moves monotonically or discontinuously with the suspected cliff: lock wait, HITM, context switches, tracepoint counts, syscall latency, page faults, reclaim, block latency, rstat flush count/time, or hot-symbol share should change at the same dimension where benchmark behavior changes.
- If monitor overhead changes the benchmark shape, split the experiment into a low-overhead scaling run and a high-detail diagnostic run at the few relevant points, then connect them explicitly.
- A named `performance-patterns` fix requires the specific evidence demanded by that pattern file. For example, false sharing needs c2c HITM/offset proof; per-CPU stats needs true-sharing counter proof; TTAS needs lock/CAS evidence; mutex-to-rwlock needs lock evidence and read-mostly source semantics.
- If the bottleneck is device flush latency, scheduler sleep, external serialization, or missing permission rather than CPU/cache-line contention, say so and avoid forcing a pattern.
- Keep negative evidence: explicitly list tempting patterns that were ruled out and why.

## Reports

At the end, write both reports under the refinement result directory or another user-specified location:

- `refine-summary.md/html`: concise executive summary with final hypotheses, status, confidence, best evidence, rejected hypotheses, recommended next actions, and links.
- `refine-detailed.md/html`: full iteration log with configs, commands, run IDs, parameter changes, monitor data, linux-perf/performance-patterns interpretation, source/upstream correlation, validation gaps, and patch/backport implications.

Both reports must include configuration-adaptation content:

- Summary report: a compact "Refinement Adaptations" table with hypothesis, changed config fields, added/removed monitors, expected signal, observed signal, and conclusion.
- Detailed report: one subsection per iteration containing the adaptation plan before the run, the exact temporary config path, the diff or field-level changes from the previous/original config, monitor additions/removals and their purpose, expected-vs-observed evidence, and the next adaptation decision.
- If a useful adaptation was not run, list it under "Proposed But Not Collected" with the blocking reason and the exact monitor/config change that would be needed.
- When the workflow spans several related benchmarks, add a cross-benchmark adaptation matrix showing which single-purpose runs explain which part of the aggregate benchmark and which config/monitor changes isolated that mechanism.

Reports must link:

- original and temporary configs;
- every complete result HTML/CSV/report used;
- RFC patch files and patch support documents, or `patch-deferred.md` if no safe patch was produced;
- generated per-run and cross-run analysis HTML;
- relevant `deps/linux` and `deps/linux-upstream` source paths;
- perf/monitor artifacts when practical.

Before finishing, render Markdown to HTML and run local Markdown link checks. Missing artifacts must be written as `missing`, not linked. The final report must state whether the RFC patch applied cleanly, whether the affected object compiled, and whether the patch was left applied or reverted after testing.
