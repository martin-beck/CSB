---
name: csb-analysis
description: "Use when analyzing existing CSB result artifacts in a results/ directory: per-run benchmark folders with matching .json/.html/.csv artifacts, saved monitor captures from perf, lock contention, Arm SPE, iostat, mpstat, bpftrace, and requests to explain process/container scaling degradation or correlate observed hot paths with existing local Linux source trees."
---

# CSB Analysis

Use this skill only for post-run CSB result analysis. The goal is to explain where benchmark throughput starts degrading as execution units increase, which saved monitor signals move with that degradation, which kernel functions become hotter in collected perf/flamegraph evidence, and whether those paths have relevant history in already available local kernel trees.

This skill is intentionally read-only with respect to benchmark execution, applications, configurations, CSB internals, host tracing state, and kernel trees:

- Do not run benchmarks or fresh profiling campaigns.
- Do not modify applications, benchmark configs, generated CSB files, runner code, monitor setup, or CSB framework files.
- Do not clone, fetch, switch, reset, or otherwise mutate kernel source trees or external skill repositories.
- Do not change host perf, tracefs, sysctl, cgroup, Docker, NIC, or scheduler state.
- Do not prepare patch files or patch-series directories.
- If required artifacts, permissions, source trees, symbols, or monitor captures are missing, report the limitation directly instead of changing the environment to fill the gap.
- Treat every benchmark as an independent experiment unless the user explicitly requests a cross-benchmark synthesis.

Non-result-analysis material that used to live in this skill has been moved to [out-of-scope-operational-notes.md](out-of-scope-operational-notes.md). Do not follow that file during normal `csb-analysis`; it is retained only as a parking place for future skills or workflows.

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

## Prerequisits

Before workflow start, check whether `performance-patterns` is available as a skill or local reference under `deps/intel-performance-skills/skills/performance-patterns`. If it is missing and network access is permitted or approved, clone the skill bundle:

```bash
git clone https://github.com/intel/intel-performance-skills.git deps/intel-performance-skills
```

Ensure Linux source exists in `deps/linux`; this single tree is used for both tested-kernel source correlation and upstream comparison. If absent, clone Torvalds Linux before making source-code claims:

```bash
git clone https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git deps/linux
```

Identify the distribution and running kernel from the testing machine, using artifacts such as `sys-config/uname.txt`, `sys-config/os-release.txt`, `sys-config/kconfig.txt`, `/proc/version`, or other identifying commands. Add a distribution remote to `deps/linux` when the kernel is distro/vendor patched, fetch all refs from that remote, and check out the branch/tag/commit that most closely matches the running kernel before source correlation. Prefer exact distro source first, then the nearest distro branch for the same kernel series, then Torvalds main only as an explicitly approximate fallback.

Suggested remote selection:

- OpenEuler: add the matching OpenEuler kernel git remote. Branches are named with a `OLK-` prefix. For example `OLK-6.6` for kernel `6.6.0+`.
- Ubuntu/Debian packaged kernels: add the matching distro kernel git remote when available, otherwise record that package source is required.
- Fedora/RHEL/CentOS Stream: add the Fedora or CentOS Stream kernel dist-git/kernel-source remote that matches the release.
- SUSE/openSUSE: add the matching SUSE kernel source remote.
- Custom kernels such as `6.6.0+`: inspect `/proc/version`, kernel build metadata, local source paths, and any node-specific notes before deciding whether the closest branch is a local source tree, distro branch, stable branch, or Torvalds main.

Ensure the same `deps/linux` clone also has a Torvalds remote for upstream comparison. Name it `torvalds` unless that name already exists:

```bash
git -C deps/linux remote add torvalds https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git
git -C deps/linux fetch --all --tags
```


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

5. Correlate saved monitor signals with the degradation.
   - Read monitor files collected at baseline, peak/plateau, first degradation point, and largest execution-unit count.
   - For each numeric monitor series, classify its relation to throughput:
     - `inverse increase`: monitor value rises while throughput falls.
     - `direct decrease`: monitor value falls while throughput falls.
     - `direct increase`: monitor value rises while throughput rises before the cliff.
     - `inverse decrease`: monitor value falls while throughput rises before the cliff.
     - `flat/noisy`: movement is too small, inconsistent, or unsupported.
   - Prefer concrete ratios or percentage movement over vague words. Example: "`mpstat sys` rises from 18% at 16 units to 61% at 96 units while throughput falls 42% from peak."
   - Do not infer kernel source paths from monitor filenames alone. Use monitor data to form hypotheses, then locate source through symbols, call stacks, tracepoint names, syscall names, lock callers, and kernel-tree search.

6. Extract hot kernel functions from saved artifacts.
   - Use collected `perf.data`, `perf report` text, `perf script` output, `perf lock`, flamegraph folded stacks, SVG flamegraphs, lock-contention CSVs, bpftrace output, or similar artifacts when present.
   - Compare hot stacks/functions across execution-unit counts, especially baseline, peak/plateau, first degradation point, and largest count.
   - List functions that become wider or consume more samples/cycles as execution-unit count increases.
   - Prefer functions near the top of widening stacks, lock callers with growing wait, and kernel symbols whose percentage or absolute sample count increases with the throughput drop.
   - Strip compiler suffixes and offsets before source lookup, for example `.isra`, `.constprop`, `.llvm`, and `+0x...`.
   - If saved `perf.data` cannot be read or kernel symbols are unavailable due to permissions, report that limitation; do not change host perf permissions.

7. Map functions to existing local source trees.
   - Use already available kernel trees, usually `deps/linux`, for source correlation.
   - Search by exact symbol first, then by nearby wrapper/caller names from stacks:

```bash
git -C deps/linux grep -n '<function_name>'
rg -n '\\b<function_name>\\b|\\b<function_name>\\s*\\(' deps/linux
```

   - If the exact function is generated, static inline, architecture-specific, or optimized away, document the lookup path and map to the closest responsible source function or caller.
   - Do not keep a permanent mapping table in the skill. The mapping belongs in the analysis report and must cite how it was found.
   - If the local source tree is missing, incomplete, dirty, shallow, or not the tested kernel, state that source correlation is unavailable or approximate.

8. Check relevant upstream or local-history changes only when history is already available.
   - Use a local Linux git tree with enough history and an appropriate comparison ref, such as `v6.6`, `torvalds/main`, or a checked-out vendor branch.
   - Record the tree path, current commit, dirty status, selected comparison ref, and whether that ref exists locally.
   - For candidate hot functions/paths, inspect relevant commits using local history:

```bash
git -C deps/linux log --oneline --decorate <base-ref>..HEAD -- <path>
git -C deps/linux log --stat --summary <base-ref>..HEAD -- <path>
git -C deps/linux log -L :<function_name>:<path> <base-ref>..HEAD
```

   - If `git log -L` cannot resolve the function, use file-level history plus targeted `git show` around relevant commits.
   - Include only commits plausibly related to the measured hot path, lock, syscall, filesystem, memory-management path, scheduler path, network path, block path, cgroup path, or architecture path. Do not list unrelated churn as evidence of a fix.
   - If no relevant commits are found, state that no relevant local-history change was found for that function/path.

9. Write analysis reports.
   - Produce one detailed Markdown document per complete run unless the user explicitly asks for a cross-run synthesis.
   - Prefer `results/<base>_csb-analysis.md` for the main report.
   - If writing multiple run reports, prefix every analysis Markdown filename with the exact result basename where practical so reports cannot collide.
   - Do not generate HTML by default. If the user requests HTML, render Markdown with Python-Markdown and table support:

```bash
python3 -m markdown -x tables -x extra results/<analysis-file>.md > results/<analysis-file>.html
```

10. Maintain local links.
    - Link each run's original result HTML when it exists, e.g. `[result html](benchmark_<...>.html)`.
    - Link generated analysis Markdown from summaries, e.g. `[analysis markdown](benchmark_<...>_csb-analysis.md)`.
    - Link generated analysis HTML only when HTML output was requested and the file exists.
    - Link Linux source files referenced in source-correlation tables or notes, using paths relative to the report location, e.g. `[fs/sync.c:180](../deps/linux/fs/sync.c#L180)`.
    - Resolve every Markdown link from the file that contains it; missing original result HTML or optional generated analysis HTML must be marked as `missing`, not linked.

## Runner Comparison Reports

Use `bm-runner/analyze.py` only as a post-run result summarizer for existing CSB result CSVs. Treat it as a convenience post-processor, not as a replacement for the per-run evidence workflow above, and do not use it to run benchmarks or modify configurations.

The script:

- recursively discovers `.csv` files under supplied folders;
- expects default CSB benchmark result CSV columns such as `algo_name`, `throughput_min`, `container_cnt`, `univ_succ_percent`, `kernel`, `execution_type`, `hostname`, and `nb_threads`;
- groups by benchmark, execution type, hostname, kernel, and thread count;
- averages throughput and success percent per `container_cnt`;
- computes `linearity` as throughput relative to the smallest container count in the same group;
- writes `analysis-results-<timestamp>/` with combined `results.csv`, `results.md`, `results.html`, per-benchmark text tables, PNG plots, and `linearity.md`.

Before using it, avoid these known traps:

- Do not point it at a full `results/` tree unless you first filter/copy only top-level benchmark result CSVs. It recursively picks up monitor CSVs such as `lock-contention.csv` and can crash with missing columns like `algo_name`.
- Ensure `tabulate` is installed, because pandas `to_markdown()` requires it and `requirements.txt` may not list it.
- If no valid benchmark CSVs remain, expect `pd.concat()` to fail; report this as "no valid CSB benchmark result CSVs" instead of treating it as an analysis result.
- Do not interpret its `linearity` column as scaling efficiency unless verified. As implemented it is speedup relative to the smallest container count, not `throughput(N) / (throughput(1) * N)`.
- Keep `noise`, `initial_size`, and other omitted dimensions in mind. The script currently groups by `algo_name`, `execution_type`, `hostname`, `kernel`, and `nb_threads`; if other dimensions vary, analyze manually or keep inputs separated.
- Guard against zero baseline throughput before relying on linearity output.

## Evidence Rules

- Benchmark throughput is the primary signal. Monitor data explains it; monitor data does not replace it.
- Use baseline, peak/plateau, first degradation point, and maximum execution-unit point as the minimum comparison set when data exists.
- Compare by `execution_type`, `container_cnt`, `nb_threads`, `noise`, and `initial_size`; do not collapse dimensions unless they are constant.
- Keep native and container execution types separate unless explicitly comparing them.
- Recompute baselines and degradation independently for each complete run; never carry baseline values, missing-monitor assumptions, hot-symbol rankings, or bottleneck hypotheses from one benchmark/run into another.
- Use saved monitor data as explanatory evidence, not as a replacement for benchmark output.
- Call out missing monitors, empty files, failed monitor commands, failed perf captures, unresolved symbols, and permission-limited artifacts.
- Do not claim a kernel root cause from one signal alone. Require at least a benchmark inflection plus matching monitor movement plus plausible stack/function/source evidence.
- Treat upstream or vendor history as "possibly relevant" unless a commit clearly changes the measured path in a way that matches the bottleneck.
- Prefer local Markdown links for result HTML, monitor files, source paths, and generated kernel-change artifacts.
- In cross-run summaries, rank evidence strength separately from observed degradation. A severe throughput cliff with missing monitor/source evidence is a high-degradation result, but not a high-confidence source attribution.

## Monitor Triage

Prioritize:

- `perf.log`, `perf.err`, `perf.data`: cycles, instructions, context switches, task-clock, stalled cycles, and hot kernel symbols. If saved `perf.data` cannot be read or symbols are unresolved, report the limitation.
- `lock-contention.csv`, `perf-lock.log`: contended lock sites, total wait, average wait, caller, and lock class.
- `mpstat.json`: system time, iowait, softirq, interrupts, RCU, scheduler activity, and idle collapse.
- `iostat*.json`, `iostat*.log`, `iostat*.txt`: device utilization, queue depth, await, service time, and throughput.
- Arm SPE captures: memory latency, cache/TLB misses, branch behavior, and load/store source attribution.
- `bpftrace*`: syscall, tracepoint, kprobe, lock, scheduler, block, or network aggregations. Read script text as part of interpreting the output.
- Existing linux-perf/performance-patterns artifacts when already present: IPC/cache/branch/context-switch counters, dual-profile baseline-vs-cliff comparisons, `perf c2c` HITM tables, `perf annotate` instruction clusters, and explicit pattern matches or non-matches.

## Report Shape

Use the structure for each benchmark from the template `template-csb-analysis-report.md`

The report may include more detail, but it must answer these questions directly:

- At what execution-unit count does throughput start dropping?
- Which monitor values rise as throughput falls?
- Which monitor values fall as throughput falls?
- Which kernel functions/stacks become wider or hotter as execution-unit count increases?
- Has each hot path changed in the available local kernel history?
- Where are the detailed per-function kernel-change notes stored?

## Practical Commands

These commands are examples for inspecting existing artifacts, not running benchmarks or changing the environment. Adapt them to the actual result layout.

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

Read saved perf data when present and permitted:

```bash
perf report --stdio -i results/<base>/<dims>/perf.data --sort symbol,dso --percent-limit 0.5
perf script -i results/<base>/<dims>/perf.data
```

Search source dynamically:

```bash
git -C deps/linux grep -n '<function_name>'
rg -n '\\b<function_name>\\b|\\b<function_name>\\s*\\(' deps/linux
```

Check already available local kernel history:

```bash
git -C deps/linux rev-parse --short HEAD
git -C deps/linux log --oneline <base-ref>..HEAD -- <path>
git -C deps/linux log -L :<function_name>:<path> <base-ref>..HEAD
```

Optionally render Markdown to HTML when requested. Use Python-Markdown with table support so pipe tables render correctly:

```bash
python3 -m markdown -x tables -x extra results/<base>_csb-analysis.md > results/<base>_csb-analysis.html
```

## Cross-Benchmark Summary

Only create a cross-benchmark summary when requested or when the user asks for "all results." Keep it separate from per-benchmark reports. The summary should rank benchmarks by:

- severity of throughput degradation;
- clarity of execution-unit inflection point;
- strength of monitor correlation;
- strength of perf/flamegraph/lock evidence;
- plausibility of source correlation;
- existence and relevance of locally available kernel-history changes;
- confidence in the result-analysis hypothesis.

Do not rank source attribution confidence from throughput loss alone.
