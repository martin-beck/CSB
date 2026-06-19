---
name: csb-analysis
description: "Analyze CSB benchmark result directories by correlating throughput degradation with execution-unit count, collected monitor data, perf/flamegraph hot paths, and Linux kernel changes since v6.6. Use for post-run evidence analysis, bottleneck triage, and upstream/backport investigation."
---

# CSB Analysis

Use this skill for post-run CSB analysis. The goal is to explain where benchmark throughput starts degrading as execution units increase, which collected monitor signals move with that degradation, which kernel functions become hotter in perf/flamegraph evidence, and whether those kernel paths have changed upstream since Linux v6.6.

This skill is intentionally self-contained:

- Do not use Python helper scripts from this skill.
- Do not create or rely on a fixed monitor-name to source-path mapping file.
- Infer source paths from the actual symbols, call stacks, monitor contents, benchmark configuration, and kernel trees available in the workspace.
- Treat every benchmark as an independent experiment unless the user explicitly requests a cross-benchmark synthesis.

## Inputs

Start from the CSB repository root unless the user gives another path. A complete benchmark result normally has:

- `results/<base>/` with per-parameter monitor artifacts.
- `results/<base>.csv` with benchmark output.
- `results/<base>.json` with the copied run configuration.
- `results/<base>.html` with result plots.

Monitor artifacts are usually nested by dimensions such as:

```text
nb_threads-*/noise-*/initial_size-*/container_cnt-*/execution_type-*/run-*/
```

Preserve those dimensions in every conclusion. Evidence from one `container_cnt`, `execution_type`, thread count, noise value, or initial size is not evidence for another point unless explicitly aggregated and stated.

## Core Workflow

For each benchmark/run:

1. Verify result completeness.
   - Identify the result basename and sibling CSV, JSON, HTML, and monitor directory.
   - Report missing artifacts directly and avoid unsupported conclusions from absent data.

2. Identify the execution-unit axis.
   - Prefer the benchmark CSV dimension that actually changes, commonly `container_cnt`.
   - If the run varies `nb_threads`, process count, or another execution-unit field instead, use that field and name it consistently.
   - Keep `execution_type`, `nb_threads`, `noise`, `initial_size`, `kernel`, host, and benchmark name separated unless they are constant.

3. Establish the throughput signal.
   - Prefer `throughput_min` for conservative degradation analysis when present.
   - If another throughput column is the only valid signal, state why it was chosen.
   - Track success and latency columns, such as `univ_succ_percent`, `univ_avg`, `univ_min`, and `univ_max`, when present.

4. Find degradation points.
   - Compute throughput by execution-unit count for each independent dimension group.
   - Identify the peak or plateau, then the first point where throughput drops materially.
   - Use explicit thresholds in the report. A useful default is: first point after the peak where throughput is at least 10% below peak, or where marginal scaling becomes negative and remains negative.
   - Record degradation against both the smallest execution-unit count and the peak/plateau when possible.

5. Correlate monitor signals with the degradation.
   - Read the monitor files collected at baseline, peak/plateau, first degradation point, and largest execution-unit count.
   - For each numeric monitor series, classify its relation to throughput:
     - `inverse increase`: monitor value rises while throughput falls.
     - `direct decrease`: monitor value falls while throughput falls.
     - `direct increase`: monitor value rises while throughput rises before the cliff.
     - `inverse decrease`: monitor value falls while throughput rises before the cliff.
     - `flat/noisy`: movement is too small, inconsistent, or unsupported.
   - Prefer concrete ratios or percentage movement over vague words. Example: "`mpstat sys` rises from 18% at 16 units to 61% at 96 units while throughput falls 42% from peak."
   - Do not infer kernel source paths from monitor filenames alone. Use monitor data to form hypotheses, then locate source through symbols, call stacks, tracepoint names, syscall names, lock callers, and kernel-tree search.

6. Extract hot kernel functions.
   - Use collected `perf.data`, `perf report`, `perf script`, `perf lock`, flamegraph folded stacks, SVG flamegraphs, lock-contention CSVs, bpftrace output, or similar artifacts when present.
   - Compare hot stacks/functions across execution-unit counts, especially baseline, peak/plateau, first degradation point, and largest count.
   - List functions that become wider or consume more samples/cycles as execution-unit count increases.
   - Prefer functions near the top of widening stacks, lock callers with growing wait, and kernel symbols whose percentage or absolute sample count increases with the throughput drop.
   - Strip compiler suffixes and offsets before source lookup, for example `.isra`, `.constprop`, `.llvm`, and `+0x...`.

7. Map functions to source dynamically.
   - Use the available kernel tree, usually `deps/linux`, for tested-source correlation.
   - Search by exact symbol first, then by nearby wrapper/caller names from stacks:

```bash
git -C deps/linux grep -n '<function_name>'
rg -n '\\b<function_name>\\b|\\b<function_name>\\s*\\(' deps/linux
```

   - If the exact function is generated, static inline, architecture-specific, or optimized away, document the lookup path and map to the closest responsible source function or caller.
   - Do not keep a permanent mapping table in the skill. The mapping belongs in the analysis report and must cite how it was found.

8. Check kernel changes since v6.6.
   - Use a Linux git tree with history and a `v6.6` tag. Prefer `deps/linux-upstream` for upstream history if present; otherwise use the available `deps/linux` tree if it has enough history.
   - Record the tree path, current commit, dirty status, and whether `v6.6` exists locally.
   - For every candidate hot function/path, inspect relevant commits since `v6.6`:

```bash
git -C deps/linux-upstream log --oneline --decorate v6.6..HEAD -- <path>
git -C deps/linux-upstream log --stat --summary v6.6..HEAD -- <path>
git -C deps/linux-upstream log -L :<function_name>:<path> v6.6..HEAD
```

   - If `git log -L` cannot resolve the function, use file-level history plus targeted `git show` around relevant commits.
   - Include only commits plausibly related to the measured hot path, lock, syscall, filesystem, memory-management path, scheduler path, network path, block path, cgroup path, or architecture path. Do not list unrelated churn as evidence of a fix.
   - If no relevant commits are found, state: "no relevant upstream change found since v6.6" for that function/path.

9. Dump per-function upstream findings.
   - For each function with relevant upstream changes, write a separate Markdown artifact named from the benchmark and function, for example:

```text
results/<base>/<benchmark>-<function>-kernel-changes.md
```

   - Sanitize names for filesystem safety: lowercase if helpful, replace spaces and slashes with `-`, and keep function names recognizable.
   - Include commit hashes, subjects, dates, touched files, a short description of each change, and why it may or may not affect the observed CSB degradation.
   - Link this artifact from the main benchmark analysis report.

10. Write the benchmark analysis report.
    - Produce one report per benchmark/run unless the user asks otherwise.
    - Prefer `results/<base>_csb-analysis.md` for the main report.
    - If generating HTML is useful and Python-Markdown is available, render with the `tables` extension so pipe tables become HTML tables. Create an adjacent HTML file with the same stem.

## Report Shape

Use this structure for each benchmark:

```markdown
# <benchmark/run> CSB Analysis

## Result Identity
- run:
- benchmark:
- kernel:
- host/architecture:
- result artifacts:

## Throughput Degradation
In benchmark `<name>` we observe that throughput starts dropping when `<execution-unit>` is >= `<Y>`.

| execution units | throughput | vs baseline | vs peak | success | latency | notes |
| --- | ---: | ---: | ---: | ---: | ---: | --- |

## Monitor Correlation
Monitor values that inversely increase as throughput drops:

| monitor | baseline | peak | degradation point | largest count | relation | interpretation |
| --- | ---: | ---: | ---: | ---: | --- | --- |

Monitor values that directly decrease as throughput drops:

| monitor | baseline | peak | degradation point | largest count | relation | interpretation |
| --- | ---: | ---: | ---: | ---: | --- | --- |

Other monitor signals:

| monitor | movement | interpretation |
| --- | --- | --- |

## Widening Kernel Functions
These are the functions where more cycles/samples/wait appear as execution units increase:

| function | evidence | source path | upstream since v6.6 | notes |
| --- | --- | --- | --- | --- |

## Kernel Change Artifacts
- `<function>`: `[kernel changes](<benchmark>-<function>-kernel-changes.md)`

## Hypothesis
State the likely bottleneck, confidence, and evidence limitations.

## Validation Plan
List the smallest rerun or profiling matrix needed to confirm or reject the hypothesis.
```

The report may include more detail, but it must answer these questions directly:

- At what execution-unit count does throughput start dropping?
- Which monitor values rise as throughput falls?
- Which monitor values fall as throughput falls?
- Which kernel functions/stacks become wider or hotter as execution-unit count increases?
- Has each hot path changed upstream since Linux v6.6?
- Where are the detailed per-function kernel-change notes stored?

## Evidence Rules

- Benchmark throughput is the primary signal. Monitor data explains it; monitor data does not replace it.
- Use baseline, peak/plateau, first degradation point, and maximum execution-unit point as the minimum comparison set when data exists.
- Keep native and container execution types separate unless explicitly comparing them.
- Keep each benchmark independent. Do not reuse source mappings, function rankings, monitor interpretations, or degradation thresholds from another benchmark without recomputing.
- Call out missing, empty, failed, or permission-limited monitor artifacts.
- Do not claim a kernel root cause from a single metric. Require a throughput inflection plus matching monitor movement plus plausible stack/function/source evidence.
- Treat upstream history as "possibly relevant" unless a commit clearly changes the measured path in a way that matches the bottleneck.
- Prefer local Markdown links for result HTML, monitor files, source paths, and generated kernel-change artifacts.

## Practical Commands

These commands are examples, not mandatory helpers. Adapt them to the actual result layout.

Discover complete results:

```bash
find results -maxdepth 1 -type f -name '*.csv' -print
```

Inspect CSV columns:

```bash
head -n 1 results/<base>.csv
```

Find monitor artifacts for a run:

```bash
find results/<base> -type f | sort
```

Read saved perf data when present:

```bash
perf report --stdio -i results/<base>/<dims>/perf.data --sort symbol,dso --percent-limit 0.5
perf script -i results/<base>/<dims>/perf.data
```

If kernel symbols are hidden and the task depends on them, request the needed permission and rerun offline perf reporting with the least broad command that resolves symbols.

Search source dynamically:

```bash
git -C deps/linux grep -n '<function_name>'
rg -n '\\b<function_name>\\b|\\b<function_name>\\s*\\(' deps/linux
```

Check upstream history since v6.6:

```bash
git -C deps/linux-upstream rev-parse --short HEAD
git -C deps/linux-upstream tag --list v6.6
git -C deps/linux-upstream log --oneline v6.6..HEAD -- <path>
git -C deps/linux-upstream log -L :<function_name>:<path> v6.6..HEAD
```

Render Markdown to HTML when useful:

```bash
python3 -m markdown -x tables results/<base>_csb-analysis.md > results/<base>_csb-analysis.html
```

## Cross-Benchmark Summary

Only create a cross-benchmark summary when requested or when the user asks for "all results." Keep it separate from per-benchmark reports. The summary should rank benchmarks by:

- severity of throughput degradation;
- clarity of execution-unit inflection point;
- strength of monitor correlation;
- strength of perf/flamegraph/lock evidence;
- plausibility of source correlation;
- existence and relevance of upstream changes since v6.6;
- confidence that a kernel patch or backport would improve many-core scaling.

Do not rank patch opportunity from throughput loss alone.
