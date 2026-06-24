---
name: csb-refine
description: "Use when a CSB benchmark needs an iterative kernel-performance refinement loop: run or rerun CSB, collect perf/all-available-monitor evidence, analyze bottlenecks with csb-analysis plus linux-perf and performance-patterns, adapt temporary benchmark configs for runtime, instance counts, native/container mode, monitors, perf/tracefs settings, bpftrace probes, temporary host-stat monitors, and continue refined runs without self-imposed continuation stops until either a clear many-core kernel data-structure congestion signal emerges or multiple thorough runs confidently rule out kernel-code scalability issues. For SSH/remote benchmark hosts, use csb-remote alongside this skill. Create and object-build-test an RFC-style kernel patch for the most likely optimization when a kernel-side signal is found, and produce concise and detailed refined reports."
---

# CSB Refine

Iteratively refine CSB benchmark evidence until each plausible kernel bottleneck from a benchmark is either supported with the best available monitor data or ruled out, then draft and object-build-test a likely kernel optimization patch in RFC style. This skill coordinates existing skills; it does not replace them.

## Required Skill Coordination

Use these skills in order as needed:

1. `csb`: for config selection/adaptation, temporary run configs, monitor setup, perf/tracefs host prep, and running/replotting CSB.
2. `csb-analysis`: for complete-run detection, per-run reports, cross-run summaries, source correlation, upstream comparison, patch/backport direction, and link checks.
3. `linux-perf`: for perf permission setup, Flow D-style scaling, perf stat/report/annotate/c2c/tracepoint collection, and dual-profile reasoning.
4. `performance-patterns`: for deciding which named patterns match or do not match, and for reading the relevant pattern detail files before suggesting fixes.
5. `csb-remote`: when benchmark execution, analysis reruns, monitor collection, dependency installation, source checkout, or object-build testing happens on one or more SSH remote hosts.

If `linux-perf` or `performance-patterns` is not available but `deps/intel-performance-skills/skills/<skill>/SKILL.md` exists, read the local skill files. If the local tree is missing and network access is approved, clone `https://github.com/intel/intel-performance-skills.git` into `deps/intel-performance-skills`.

For remote refinement, the controller host supplies the skills and orchestration, but every benchmark sweep, cleanup, monitor run, permission change, package install, source checkout/update, analysis command that depends on remote artifacts, and kernel object build must execute on the remote. Copy final reports, configs, generated bpftrace programs, monitor artifacts, logs, and patches back using the layout in `csb-remote`.

## Persistence

- From the first start of a refinement task, continue through the full workflow until all required runs, analyses, reports, patch/deferred-patch artifacts, and validation steps are finished.
- Do not stop merely because a certain amount of wall-clock time has passed, a session has become long, or the next step would normally be phrased as a continuation. Continue with the next concrete action instead of asking whether to proceed.
- Stop only when the refinement is complete, the user explicitly interrupts or changes the objective, host/tooling permissions create a concrete blocker that cannot be worked around, or an explicit user-provided run/budget limit is reached.

## Many-Core Burden Of Proof

- Be very thorough for many-core scalability tasks. Treat "many core" as hundreds of cores, not merely tens, and design runs that can stress that regime when the host has enough CPUs or when safe oversubscription can approximate the pressure.
- Do not stop at a weak or ambiguous result. The final outcome must be one of:
  - a clear, reproducible signal of kernel-side congestion tied to a specific data structure, lock, hierarchy, accounting path, refcount/atomic, cache line, or traversal that should plausibly be improved in kernel code;
  - a confident negative finding, supported by multiple different and thorough focused runs, that this benchmark/test is unlikely to run into kernel-code scalability issues on many-core systems.
- Oversubscribe CPU cores heavily when necessary to expose contention, while explicitly accounting for the natural scaling degradation that begins once runnable work exceeds available physical cores. Reports must separate expected oversubscription effects from kernel data-structure congestion.
- Negative conclusions require stronger evidence than positive leads: include low-overhead scaling shape, at least one high-detail diagnostic run at the highest practical pressure point, monitor-overhead checks, and source-path/perf evidence showing that hot time is not accumulating in scalable kernel data structures.
- If a run does not create enough parallel pressure on kernel paths, increase process/container/thread counts, reduce nonessential monitor overhead, adjust duration, or vary benchmark arguments before concluding that there is no many-core kernel bottleneck.

## Refinement Loop

For each requested benchmark or initial config:

1. **Baseline run or locate existing run**
   - If a complete result already exists, start from it.
   - Otherwise run CSB using `csb`, with normal result siblings `<run>/`, `<run>.json`, `<run>.html`, and `<run>.csv`.
   - Before perf-backed runs, try to set `perf_event_paranoid=-1` and check/remount tracefs as described in `csb`/`csb-analysis`. If blocked, record the exact limitation.

2. **Clean between CSB sweeps**
   - After every CSB benchmark sweep, and before starting any new CSB sweep, perform an explicit cleanup pass so the next run starts from a relatively clean system state.
   - Clean only stale artifacts that belong to the previous CSB/refinement sweep. Preserve completed result directories, copied configs, reports, source changes, and unrelated user work unless the user explicitly asks to remove them.
   - Check and remove leftover workload processes, runtime/container state, monitor processes, temporary monitor output, start-barrier files, lock files, and scratch directories that can affect the next run. Typical examples include:
     - benchmark/application processes such as stale native workers, external benchmark helpers, runtime children, or aborted container lifecycle processes;
     - container runtime state for the benchmark namespace, such as stopped or half-deleted `runc`/`youki`/Docker containers with the benchmark's name prefix;
     - monitor processes such as `perf`, `perf lock`, `bpftrace`, `mpstat`, `iostat`, temporary shell monitors, and their oversized or partial temp files;
     - CSB barrier or scratch files such as `build/bench/start`, per-run app stdout/stderr leftovers, temporary config copies, and temporary result staging directories not meant to be kept.
   - Prefer benchmark-specific cleanup commands over broad destructive cleanup. When a benchmark has its own cleanup script or runtime delete command, use that first; only remove runtime directories directly when the runtime cannot clean stale state and the path clearly belongs to the interrupted CSB sweep.
   - Re-check after cleanup that no matching stale processes or runtime entries remain. If cleanup cannot fully complete, record the remaining state and decide whether the next sweep would be contaminated before running it.
   - Include the cleanup command summary and any leftovers in the detailed report's iteration log.

3. **First analysis**
   - Run `csb-analysis` on the complete result.
   - Extract every plausible kernel bottleneck hypothesis from the report: subsystem, benchmark dimensions, inflection point, hot symbols, monitor gaps, linux-perf classification, performance-pattern match/non-match, confidence, and missing evidence.
   - For each hypothesis, state the exact evidence gap that prevents a sharper conclusion. Prefer gaps that can be closed by changing the CSB configuration or monitor set, such as missing cliff-adjacent counts, too-short runtime, missing lock/HITM/tracepoint data, mixed native/container effects, missing CPU isolation, or monitor overhead hiding the signal.
   - Keep hypotheses separate. Do not merge native/container or different instance/thread/noise/initial-size dimensions unless the evidence supports it.

4. **Design a temporary focused config and expected signal**
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
   - If system CPU utilization is too low to expose kernel contention, increase load before concluding there is no bottleneck:
     - add larger native-process or container counts, including counts above the physical-core count when memory permits;
     - keep a few points below, at, and above the physical-core boundary so the report can separate kernel bottleneck behavior from the expected total-throughput shape change after cores saturate;
     - for many-core investigations, include counts representative of hundreds of cores when hardware permits, and use heavier oversubscription only as an experimental stressor whose expected scheduling/throughput degradation is labeled separately from kernel congestion;
     - prefer increasing independent processes/containers over changing benchmark semantics unless the hypothesis specifically requires thread-count variation.
   - For every scaled-load config, estimate and monitor total memory use before and during the run. Use cgroup memory counters, `/proc/meminfo`, PSI, `free`, `smem`, or another host-appropriate signal. Reduce process/container counts, duration, initial size, or monitor set if projected or observed memory use approaches the system limit; avoiding OS shutdown or OOM side effects takes priority over completing a point.
   - When the first run is too broad or noisy, narrow the next config so the result clearly separates "hypothesis true" from "hypothesis false". Examples: use only baseline/peak/cliff counts for `perf c2c`; only cliff points for scheduler tracepoints; adjacent counts around a throughput cliff for lock contention; native-vs-container paired points when runtime overhead is suspected.
   - Prefer focused reruns over broad sweeps once an inflection is known.

5. **Monitor selection by hypothesis**
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

6. **Rerun and re-analyze**
   - Run the temporary config.
   - Before this run, perform the "Clean between CSB sweeps" step if any prior sweep has run in the current refinement session.
   - Generate fresh per-run and cross-run analysis.
   - Compare new evidence against the previous hypothesis:
     - confirmed: benchmark inflection, monitor signal, source path, and pattern classification align;
     - weakened: new evidence points elsewhere or removes the suspected signal;
     - blocked: permission/tooling prevents required evidence collection;
     - split: multiple bottlenecks are visible and need separate focused configs.
   - If the new evidence is still too diffuse, do not just repeat the same run. Propose the next sharper config/monitor change or explain why no CSB-accessible configuration can isolate the bottleneck further.

7. **Iterate**
   - For each confirmed or still-plausible hypothesis, refine the config again to close the largest remaining evidence gap. Continue with further refined runs until a clear signal for a kernel data-structure bottleneck emerges, the hypothesis is ruled out, or a concrete blocker prevents better evidence.
   - A clear signal normally requires the same dimension change to align across benchmark behavior, system CPU or kernel-time pressure, and at least one targeted monitor/source-path signal such as lock wait, cache-line sharing, refcount/atomic pressure, RCU/kernfs/cgroup traversal, rstat flush activity, slab/page-cache activity, syscall latency, or a hot kernel symbol tied to the suspected data structure.
   - If system CPU utilization remains low after a focused run, do not stop at a weak negative result. Increase process/container counts, reduce monitor overhead, or adjust benchmark arguments to put enough parallel pressure on the kernel path, while preserving memory headroom.
   - For many-core tasks, keep iterating until the evidence is strong enough for one of the two final outcomes in "Many-Core Burden Of Proof." A merely smooth curve at low or moderate core counts is not enough to rule out many-core kernel scalability issues.
   - Stop iterating on a hypothesis when one of these is true:
     - the required evidence has been collected for benchmark behavior, monitor signal, source path, and pattern classification;
     - the hypothesis is contradicted by multiple focused reruns that reach sufficient many-core or oversubscribed pressure and use different evidence channels;
     - remaining evidence requires unavailable host permissions/hardware/tooling;
     - additional reruns would repeat the same evidence without changing confidence;
     - the user-specified time/run budget is exhausted.

8. **Continue across hypotheses**
   - Process every plausible kernel bottleneck extracted from the benchmark.
   - If fixing or validating one hypothesis exposes a new bottleneck in later reruns, add it to the queue and mark its source run.

9. **Create an RFC kernel patch after successful refinement**
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

10. **Apply and object-build-test the patch temporarily**
   - Temporarily apply the RFC patch to the target kernel tree, preserving unrelated user changes. Prefer `git apply --check` first, then apply the patch.
   - Compile the affected object or narrow subsystem target rather than a full kernel unless the user requested a full build. Examples: `make M=<subdir> <file>.o`, `make kernel/cgroup/cgroup.o`, or the closest valid target for the edited file.
   - If the object build fails, fix the patch and retest when the failure is patch-related. If the failure is environmental or pre-existing, record the exact command and error.
   - After the compile test, leave the workspace in a clear state:
     - either keep the patch applied only when the user asked for an applied tree or the workflow needs it for immediate validation;
     - otherwise reverse only the patch changes you made, leaving unrelated dirty files untouched, and keep the patch file as the deliverable.
   - Record the apply command, build command, build result, and tree state in the detailed report.

11. **Patch support documents**
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

## Refresh Configs Or Generated Headers

For ordinary CSB configs, edit JSON under `config/` and rerun/replot with the commands above.

For syzkaller-generated headers/configs under `bench/targets/<group>/syz` and `config/<group>`, use `csb-syzkaller`; do not manually edit generated files unless the user explicitly wants a temporary experiment.

## Usage Validation

For config-only changes:

```bash
python3 -m json.tool config/<file>.json >/dev/null
```

For real validation, run a short/small config first: one repeat, low duration, one or two execution-unit counts, and monitors disabled if you only need application wiring.

## Evidence Rules

- A severe scaling drop is not enough. Require benchmark inflection plus a matching monitor signal plus plausible kernel source path before raising confidence.
- The main target is kernel data-structure bottlenecks. Prefer evidence that points to a contended or inefficient data structure, traversal, accounting path, reference count, lock, cache line, rbtree/list/hash/radix/xarray use, cgroup/kernfs hierarchy, slab/page-cache structure, or similar kernel object. If evidence points instead to device latency, benchmark userspace, or monitor overhead, say so and keep refining or rule out the data-structure hypothesis.
- For many-core scalability, distinguish three things explicitly: expected saturation/oversubscription degradation, userspace or device limits, and kernel data-structure congestion. Only the last justifies kernel optimization work.
- A confident "no many-core kernel scalability issue" conclusion requires converging negative evidence across multiple run shapes and monitor channels, not just absence of one hot symbol or one flat/clean result.
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
- Detailed report: include a "Monitor Decision Log" per hypothesis listing all available CSB monitors considered, bpftrace programs reused/adapted/created, non-CSB kernel statistics queried, temporary monitor scripts or commands, missing software and any local installs, and why each collected signal was sufficient or insufficient.
- Detailed report: include a "Load, CPU, and Memory Guardrails" subsection for each scaled run with physical-core count, selected process/container counts, whether counts exceed physical cores, expected throughput-shape implications, observed system CPU/kernel time, memory limit, peak memory, and any monitor or argument changes made to avoid overhead or OOM risk.
- Detailed report: for many-core tasks, include a "Many-Core Conclusion" subsection stating whether the final result is a kernel-side congestion signal or a confident negative finding, the highest physical-core-equivalent and oversubscribed pressure tested, which evidence channels agree, and how natural oversubscription degradation was separated from kernel data-structure bottlenecks.
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
