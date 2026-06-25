---
name: csb-refine
description: "Use when a CSB benchmark needs an iterative kernel-performance refinement loop: run or rerun CSB, analyze bottleneck hypotheses with csb-analysis plus linux-perf/performance-patterns when available, adapt temporary configs and monitors, rerun focused validation points, and continue until a kernel bottleneck, hardware/userspace/device limit, permission blocker, or confident negative result is established. For SSH or remote benchmark hosts, use csb-remote alongside this skill. When a kernel-side signal is found, create the most likely RFC-style kernel patch, object-build-test it, and produce concise and detailed refined reports."
---

# CSB Refine

Coordinate existing CSB skills to turn a benchmark result into a defensible conclusion. Keep this skill lean: use `csb` for running and monitor setup, `csb-analysis` for result/source/patch-artifact mechanics, `linux-perf` and `performance-patterns` when available for profiler interpretation, and `csb-remote` when any benchmark or build step happens over SSH.

## Operating Rules

- Continue from the first refinement step until reports, patch or deferred-patch artifacts, and validation notes are complete, unless the user interrupts, a concrete blocker prevents progress, or an explicit budget is reached.
- Preserve original configs, generated headers, completed results, reports, source changes, and unrelated user work. For syzkaller-generated headers/configs, use the relevant generator workflow; do not hand-edit generated files unless the user explicitly asks for a temporary experiment.
- For ordinary configs, copy JSON to a clearly temporary path such as `config/refine/`, edit only the fields needed for the hypothesis, and validate with `python3 -m json.tool config/<file>.json >/dev/null`. For wiring checks, run a short/small config first.
- Before each new CSB sweep, clean only stale state from the previous sweep: ghost workload/container/monitor processes, stale runtime state, partial monitor temp files, start-barrier files, and lock/scratch files. Do not delete the whole `build/` directory by default; remove only clearly stale CSB run artifacts such as `build/bench/start` unless the user asks for broader cleanup.
- For remote refinement, all sweeps, cleanup, monitor collection, permission changes, source checkout/update, artifact-dependent analysis, and kernel object builds run on the remote host. Copy final reports, configs, monitor artifacts, logs, and patches back using `csb-remote` conventions.

## Refinement Loop

For each benchmark or initial config:

1. **Start from evidence.** Locate a complete existing result or run CSB with `csb`. Use the perf/tracefs preparation in `csb` when profiler evidence matters, and record unavailable permissions instead of silently weakening the run.
2. **Analyze.** Run `csb-analysis`. Extract distinct hypotheses with their benchmark dimension, inflection point, hot path or monitor signal, evidence gap, and confidence. Keep native/container and other dimensions separate unless the data justifies merging them.
3. **Plan a focused rerun.** For each active hypothesis, write the temporary config path and a short plan: changed fields, added/removed monitors, expected signal if true, expected negative evidence if false, and overhead/confounding risk.
4. **Rerun and compare.** Run the focused config, re-analyze, and classify the hypothesis as confirmed, weakened, split, blocked, or ruled out. If the result is diffuse, change the next config or monitor set; do not repeat the same run without a sharper purpose.
5. **Check monitor influence.** After reaching a conclusion, rerun the benchmark with all monitors disabled at the relevant points. Confirm that the same throughput or primary metric trend remains, or report the monitor-induced distortion.
6. **Stop with a clear outcome.** Finish when the evidence supports one of these outcomes:
   - kernel-side congestion tied to a specific source path, data structure, lock, refcount/atomic, cache line, hierarchy, accounting path, traversal, or syscall path;
   - hardware, device, scheduler sleep/wakeup, external serialization, benchmark userspace, or monitor-overhead bottleneck that should be reported rather than forced into a kernel patch;
   - confident negative result after multiple focused run shapes and evidence channels;
   - concrete permission, hardware, kernel-config, tooling, or budget blocker.

## Evidence Standard

- A throughput cliff alone is not enough. Require benchmark movement plus matching monitor/profiler evidence plus a plausible source path before claiming a kernel root cause.
- For many-core work, treat "many core" as hundreds of cores when the host can support it, or use explicitly labeled oversubscription pressure when it cannot. Separate expected saturation/oversubscription effects from kernel data-structure congestion.
- Increase process/container counts, duration, or pressure when CPU use is too low to test the suspected kernel path, but keep memory headroom. Record physical cores, selected counts, whether counts exceed cores, peak memory, and any changes made to avoid OOM or monitor overhead.
- Prefer focused low-overhead scaling runs plus high-detail diagnostic runs at baseline, peak/plateau, cliff, and largest practical points. Heavy monitors such as c2c, tracepoints, bpftrace, lock tracing, or perf sched should cover only the points needed to prove or disprove the hypothesis.
- Use `performance-patterns` only when its required evidence is present. Keep negative evidence by naming tempting patterns that were ruled out.

## Patch Work

Create a kernel patch only when a kernel-side signal is confirmed or strongly supported. For the most likely optimization, create an RFC-style patch against the source tree identified by analysis, preferably the benchmarked tree such as `deps/linux`, and object-build-test it.

- Keep the patch conservative and evidence-linked. Avoid broad subsystem rewrites or pattern fixes not supported by the measured path.
- Use a subject beginning with `[RFC PATCH]`; explain the benchmark symptom, refined evidence, affected path, intended optimization, correctness reasoning, and validation status.
- If the best direction is a backport, cite the upstream commit and adapt the smallest patch needed for the target tree.
- Test with `git apply --check`, apply temporarily, and build the affected object or narrow target. Record the apply command, build command, result, and whether the patch was left applied or reverted.
- If no responsible patch can be produced, write a deferred-patch note naming the missing evidence or semantic uncertainty instead of inventing code.

## Reports

Write final artifacts under the refinement result directory or user-specified location, using the related benchmark basename as a prefix:

- `<base>_refine-summary.md`: final hypotheses, status, confidence, best evidence, rejected hypotheses, monitor-off validation result, patch status, and recommended next actions.
- `<base>_refine-detailed.md`: iteration log with configs, commands, run IDs, changed fields, monitor decisions, expected-vs-observed evidence, source/pattern interpretation, blockers, validation gaps, and many-core CPU/memory guardrails.
- `<base>_patch-series-<theme>/...` plus patch support docs when a patch is produced, or `<base>_patch-deferred.md` when no safe patch is produced.

Reports must link existing original/temporary configs, complete result HTML/CSV/report files, generated analysis, relevant source paths, monitor artifacts when practical, and patch artifacts. Mark absent optional artifacts as `missing` rather than linking them. Validate local Markdown links before finishing.
