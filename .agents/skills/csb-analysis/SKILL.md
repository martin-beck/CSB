---
name: csb-analysis
description: "Use when analyzing existing CSB result artifacts in a results/ directory and producing the kernel patch artifacts that follow from the analysis: per-run benchmark folders with matching .json/.html/.csv artifacts, saved monitor captures from perf, lock contention, Arm SPE, iostat, mpstat, bpftrace, process/container scaling degradation, hot-path source correlation in local Linux trees, and patch/backport preparation."
---

# CSB Analysis

Use this skill for post-run CSB result analysis and the kernel patch artifacts that follow from that analysis. The goal is to explain where benchmark performance starts degrading as execution units increase, which saved monitor signals move with that degradation, which kernel functions become hotter in collected perf/flamegraph evidence, whether those paths have relevant history in already available local kernel trees, and what concrete kernel patch should be produced from the evidence.

This skill does not run new experiments or mutate benchmark inputs. It may write analysis reports and kernel patch-preparation artifacts under `results/`, but it remains read-only with respect to benchmark execution, applications, configurations, CSB internals, host tracing state, and kernel source trees:

- Do not run benchmarks or refresh profiling campaigns.
- Do not modify applications, benchmark configs, generated CSB files, runner code, monitor setup, or CSB framework files.
- Do not clone, fetch, switch, reset, or otherwise mutate kernel source trees or external skill repositories.
- Do not change host perf, tracefs, sysctl, cgroup, Docker, NIC, or scheduler state.
- If required artifacts, permissions, source trees, symbols, or monitor captures are missing, report the limitation directly instead of changing the environment to fill the gap.
- Treat every benchmark as an independent experiment unless the user explicitly requests a cross-benchmark synthesis.

Operational material that is still outside this skill has been moved to [out-of-scope-operational-notes.md](out-of-scope-operational-notes.md). Do not follow that file during normal `csb-analysis`; it is retained only as a parking place for future skills or workflows.

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

## Prerequisites

Before workflow start, check whether `performance-patterns` is available as a skill or local reference under `deps/intel-performance-skills/skills/performance-patterns`. If it is missing, record that the performance-patterns classification is unavailable; do not clone external repositories as part of this skill.

Ensure Linux source exists in `deps/linux`; this single tree is used for both tested-kernel source correlation and upstream comparison. If absent, state that source-code correlation and patch creation are blocked until a suitable local Linux tree is provided.

Identify the distribution and running kernel from the testing machine, using artifacts such as `sys-config/uname.txt`, `sys-config/os-release.txt`, `sys-config/kconfig.txt`, `/proc/version`, or other identifying commands. Prefer an already checked-out source tree or ref that matches the tested kernel. Prefer exact distro source first, then the nearest distro branch for the same kernel series, then Torvalds main only as an explicitly approximate fallback.

Useful source-selection hints when refs are already local:

- OpenEuler: use the matching OpenEuler kernel ref when available. Branches are named with a `OLK-` prefix. For example `OLK-6.6` for kernel `6.6.0+`.
- Ubuntu/Debian packaged kernels: use the matching distro package source when available, otherwise record that package source is required.
- Fedora/RHEL/CentOS Stream: use the Fedora or CentOS Stream kernel dist-git/kernel-source ref that matches the release when available.
- SUSE/openSUSE: use the matching SUSE kernel source ref when available.
- Custom kernels such as `6.6.0+`: inspect `/proc/version`, kernel build metadata, local source paths, and any node-specific notes before deciding whether the closest branch is a local source tree, distro branch, stable branch, or Torvalds main.

For upstream comparison, use an already available Torvalds remote/ref in `deps/linux`. If the needed upstream ref is not local, report that upstream comparison is unavailable or approximate instead of fetching it.

## Core Workflow

For each benchmark/run:

1. Verify result completeness.
   - Identify the result basename and sibling CSV, JSON, HTML, and monitor directory.
   - Report missing artifacts directly and avoid unsupported conclusions from absent data.

2. Identify the execution-unit axis.
   - Prefer the benchmark CSV dimension that actually changes, commonly `container_cnt`.
   - If the run varies `nb_threads`, container/process count, or another execution-unit field instead, use that field and name it consistently.
   - Keep `execution_type`, `nb_threads`, `noise`, `initial_size`, `kernel`, host, and benchmark name separated unless they are constant.

3. Establish the performance signal.
   - Check `throughput_min` for conservative degradation analysis when present.
   - If another performance column is giving a stronger signal, state why it was chosen.
   - Track all success and latency columns, such as `univ_succ_percent`, `univ_avg`, `univ_min`, and `univ_max`, when present.

4. Run CSB analyzer output as part of the analysis when practical.
   - Use the existing CSB analyzer, `bm-runner/analyze.py` (`csb-analyze` in this skill), against a directory containing only the intended top-level benchmark result CSVs.
   - Treat analyzer outputs as first-pass aggregate evidence for performance, success, kernel comparison, and drop points. They do not replace per-run monitor, perf, lock, source, and history analysis.
   - Keep analyzer artifacts linked from the report when they are created, and record when the analyzer could not be used due to missing dependencies, invalid CSV columns, or unsafe mixed inputs.
   - Do not use the analyzer to run benchmarks or modify benchmark configurations.

5. Find degradation points.
   - Compute performance by execution-unit count for each independent dimension group.
   - Identify the peak or plateau, then the first point where performance drops materially.
   - Use explicit thresholds in the report. A useful default is: first point after the peak where performance is at least 10% below peak, or where marginal scaling becomes negative and remains negative.
   - Record degradation against both the smallest execution-unit count and the peak/plateau when possible.

6. Correlate saved monitor signals with the degradation.
   - Read monitor files collected at baseline, peak/plateau, first degradation point, and largest execution-unit count.
   - For each numeric monitor series, classify its relation to performance:
     - `inverse increase`: monitor value rises while performance falls.
     - `direct decrease`: monitor value falls while performance falls.
     - `direct increase`: monitor value rises while performance rises before the cliff.
     - `inverse decrease`: monitor value falls while performance rises before the cliff.
     - `flat/noisy`: movement is too small, inconsistent, or unsupported.
   - Prefer concrete ratios or percentage movement over vague words. Example: "`mpstat sys` rises from 18% at 16 units to 61% at 96 units while performance falls 42% from peak."
   - Do not infer kernel source paths from monitor filenames alone. Use monitor data to form hypotheses, then locate source through symbols, call stacks, tracepoint names, syscall names, lock callers, and kernel-tree search.

7. Extract hot kernel functions from saved artifacts.
   - Use collected `perf.data`, `perf report` text, `perf script` output, `perf lock`, flamegraph folded stacks, SVG flamegraphs, lock-contention CSVs, bpftrace output, or similar artifacts when present.
   - Compare hot stacks/functions across execution-unit counts, especially baseline, peak/plateau, first degradation point, and largest count.
   - List functions that become wider or consume more samples/cycles as execution-unit count increases.
   - Prefer functions near the top of widening stacks, lock callers with growing wait, and kernel symbols whose percentage or absolute sample count increases with the performance drop.
   - If saved `perf.data` cannot be read or kernel symbols are unavailable due to permissions, report that limitation; do not change host perf permissions.

8. Map functions to existing local source trees.
   - Use already available kernel trees, usually `deps/linux`, for source correlation.
   - Search by exact symbol first, then by nearby wrapper/caller names from stacks:

```bash
git -C deps/linux grep -n '<function_name>'
rg -n '\\b<function_name>\\b|\\b<function_name>\\s*\\(' deps/linux
```

   - If the exact function is generated, static inline, architecture-specific, or optimized away, document the lookup path and map to the closest responsible source function or caller.
   - Do not keep a permanent mapping table in the skill. The mapping belongs in the analysis report and must cite how it was found.
   - If the local source tree is missing, incomplete, dirty, shallow, or not the tested kernel, state that source correlation is unavailable or approximate.

9. Check relevant upstream or local-history changes only when history is already available.
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

10. Write analysis reports.
   - Produce one detailed Markdown document per complete run unless the user explicitly asks for a cross-run synthesis.
   - Prefer `results/<base>_csb-analysis.md` for the main report.
   - If writing multiple run reports, prefix every analysis Markdown filename with the exact result basename where practical so reports cannot collide.
   - Do not generate HTML by default. If the user requests HTML, render Markdown with Python-Markdown and table support:

```bash
python3 -m markdown -x tables -x extra results/<analysis-file>.md > results/<analysis-file>.html
```

11. Create kernel patch artifacts after analysis.
    - Patch creation is a core result of CSB analysis when the evidence supports a concrete kernel change or backport. Produce patch artifacts after the report has identified degradation, monitor correlation, hot functions/stacks, source mapping, and local-history context.
    - Create per-run patch-series artifacts instead of editing benchmark evidence reports in place. For each run, create a descriptive folder such as `results/<base>_patch-series-ext4-fsync-flush-coalescing/` or `results/<base>_patch-series-vfs-namei-negative-lookup-cache/`.
    - Put the generated patch file and its safety/implications documentation in that folder. Use a clearly marked RFC patch when the change is hypothesis-driven and not yet validated by a rerun.
    - Add or update `results/kernel_patch_preparation_summary.md` as a concise index of all patch-series folders, with columns for run, patch series, theme, degradation, confidence, detailed report link, patch link, and original result HTML link. Missing artifacts must be written as `missing`, not linked.
    - Patch-series documents should include:
      - run identity, benchmark name, and completeness;
      - links to the local patch file, detailed Markdown report, optional generated HTML report when requested, and original result HTML when present;
      - source-correlation links to `deps/linux` paths with correct relative paths from the patch-series folder;
      - upstream-comparison notes naming the compared Torvalds or vendor ref/commit in `deps/linux`;
      - why this patch was selected and why it is expected to be profitable;
      - linux-perf/performance-patterns evidence used to select or reject this patch theme;
      - what the patch changes at the subsystem/function level;
      - whether the patch is a novel RFC change, a backport/adaptation of upstream work, or a combination;
      - safety level and assumptions;
      - implications for semantics, latency, performance, memory, fairness, crash consistency, permissions, LSM/fsnotify/accounting, cgroups, and architecture-specific behavior as applicable;
      - validation checklist and benchmark rerun matrix.
    - Patch/backport proposals must state concrete kernel change direction or upstream backport direction, affected files/functions, expected benefit, risks, validation plan, and a minimal benchmark rerun matrix.
    - Before reporting patch preparation as complete, count patch-series directories and patch files for the intended run set, ensure each patch-series directory has `README.md` and `SAFETY_IMPLICATIONS_AND_DESCRIPTION.md`, and check for stale or broken source links.

12. Maintain local links.
    - Link each run's original result HTML when it exists, e.g. `[result html](benchmark_<...>.html)`.
    - Link generated analysis Markdown from summaries, e.g. `[analysis markdown](benchmark_<...>_csb-analysis.md)`.
    - Link generated analysis HTML only when HTML output was requested and the file exists.
    - Link Linux source files referenced in source-correlation tables or notes, using paths relative to the report location, e.g. `[fs/sync.c:180](../deps/linux/fs/sync.c#L180)`.
    - Resolve every Markdown link from the file that contains it; missing original result HTML or optional generated analysis HTML must be marked as `missing`, not linked.

## CSB Analyzer And Runner Comparison Reports

Use `bm-runner/analyze.py` as the CSB analyzer (`csb-analyze`) for existing CSB result CSVs. It is part of the analysis workflow for aggregate performance and linearity checks, but it is not a replacement for the per-run evidence workflow above and must not be used to run benchmarks or modify configurations.

The script:

- recursively discovers `.csv` files under supplied folders;
- expects default CSB benchmark result CSV columns such as `algo_name`, `throughput_min`, `container_cnt`, `univ_succ_percent`, `kernel`, `execution_type`, `hostname`, and `nb_threads`;
- groups by benchmark, execution type, hostname, kernel, and thread count;
- averages performance and success percent per `container_cnt`;
- computes `linearity` as performance relative to the smallest container count in the same group;
- writes `analysis-results-<timestamp>/` with combined `results.csv`, `results.md`, `results.html`, per-benchmark text tables, PNG plots, and `linearity.md`.

Before using it, avoid these known traps:

- Do not point it at a full `results/` tree unless you first filter/copy only top-level benchmark result CSVs. It recursively picks up monitor CSVs such as `lock-contention.csv` and can crash with missing columns like `algo_name`.
- Ensure `tabulate` is installed, because pandas `to_markdown()` requires it and `requirements.txt` may not list it.
- If no valid benchmark CSVs remain, expect `pd.concat()` to fail; report this as "no valid CSB benchmark result CSVs" instead of treating it as an analysis result.
- Do not interpret its `linearity` column as scaling efficiency unless verified. As implemented it is speedup relative to the smallest container count, not `performance(N) / (performance(1) * N)`.
- Keep `noise`, `initial_size`, and other omitted dimensions in mind. The script currently groups by `algo_name`, `execution_type`, `hostname`, `kernel`, and `nb_threads`; if other dimensions vary, analyze manually or keep inputs separated.
- Guard against zero baseline performance before relying on linearity output.

## Evidence Rules

- Benchmark throughput is the primary signal if documentation beneath `doc/` does not specify a different performance metric as primary signal. An example are some `bm_external` benchmarks, which use time as primary fignal with a fixed amount of iterations. Monitor data explains it; monitor data does not replace it.
- Use baseline, peak/plateau, first degradation point, and maximum execution-unit point as the minimum comparison set when data exists.
- Compare by `execution_type`, `container_cnt`, `nb_threads`, `noise`, and `initial_size`; do not collapse dimensions unless they are constant.
- Keep native and container execution types separate unless explicitly comparing them.
- Recompute baselines and degradation independently for each complete run; never carry baseline values, missing-monitor assumptions, hot-symbol rankings, or bottleneck hypotheses from one benchmark/run into another.
- Use saved monitor data as explanatory evidence, not as a replacement for benchmark output.
- Call out missing monitors, empty files, failed monitor commands, failed perf captures, unresolved symbols, and permission-limited artifacts.
- Do not claim a kernel root cause from one signal alone. Require at least a benchmark inflection plus matching monitor movement plus plausible stack/function/source evidence.
- Treat upstream or vendor history as "possibly relevant" unless a commit clearly changes the measured path in a way that matches the bottleneck.
- Prefer local Markdown links for result HTML, monitor files, source paths, and generated kernel-change artifacts.
- In cross-run summaries, rank evidence strength separately from observed degradation. A severe performance cliff with missing monitor/source evidence is a high-degradation result, but not a high-confidence source attribution.

## Monitor Triage

Prioritize:

- `perf.log`, `perf.err`, `perf.data`: cycles, instructions, context switches, task-clock, stalled cycles, and hot kernel symbols. If saved `perf.data` cannot be read or symbols are unresolved, report the limitation.
- `lock-contention.csv`, `perf-lock.log`: contended lock sites, total wait, average wait, caller, and lock class.
- `mpstat.json`: system time, iowait, softirq, interrupts, RCU, scheduler activity, and idle collapse.
- `iostat*.json`, `iostat*.log`, `iostat*.txt`: device utilization, queue depth, await, service time, and performance.
- Arm SPE captures: memory latency, cache/TLB misses, branch behavior, and load/store source attribution.
- `bpftrace*`: syscall, tracepoint, kprobe, lock, scheduler, block, or network aggregations. Read script text as part of interpreting the output.
- Existing linux-perf/performance-patterns artifacts when already present: IPC/cache/branch/context-switch counters, dual-profile baseline-vs-cliff comparisons, `perf c2c` HITM tables, `perf annotate` instruction clusters, and explicit pattern matches or non-matches.

## Report Shape

Use the structure for each benchmark from the template `template-csb-analysis-report.md`

The report may include more detail, but it must answer these questions directly:

- At what execution-unit count does performance start dropping?
- Which monitor values rise as performance falls?
- Which monitor values fall as performance falls?
- Which kernel functions/stacks become wider or hotter as execution-unit count increases?
- Has each hot path changed in the available local kernel history?
- Where are the detailed per-function kernel-change notes stored?
- Which kernel patch or backport artifact was created from the analysis, or why no patch is justified by the evidence?

## Practical Commands

These commands are examples for inspecting existing artifacts, not running benchmarks or changing the environment. Adapt them to the actual result layout.

Discover complete results:

```bash
find results -maxdepth 1 -type f -name '*.csv' -print
```

Run CSB analyzer on a filtered folder of top-level benchmark CSVs:

```bash
cd bm-runner
TMPDIR=/tmp/csb-analyze MPLCONFIGDIR=/tmp/csb-mpl ../venv/bin/python analyze.py <csv-folder> [<csv-folder> ...]
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

- severity of performance degradation;
- clarity of execution-unit inflection point;
- strength of monitor correlation;
- strength of perf/flamegraph/lock evidence;
- plausibility of source correlation;
- existence and relevance of locally available kernel-history changes;
- confidence in the result-analysis hypothesis.

Do not rank source attribution confidence from performance loss alone.
