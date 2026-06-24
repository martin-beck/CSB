---
name: csb-analysis
description: "Use when analyzing CSB results in a results/ directory, especially per-run benchmark folders with matching .json/.html/.csv artifacts, monitor captures from perf, lock contention, Arm SPE, iostat, mpstat, bpftrace, linux-perf workflows, performance-patterns classification, or requests to explain process/container scaling degradation, correlate bottlenecks with Linux kernel source, compare distribution-kernel hot paths against Torvalds main using one deps/linux clone, or propose/backport kernel patch directions for many-core systems."
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

Before workflow start, check whether `linux-perf` is available as a skill or local reference under `deps/intel-performance-skills/skills/linux-perf`. If it is missing and network access is permitted or approved, clone the skill bundle:

```bash
git clone https://github.com/intel/intel-performance-skills.git deps/intel-performance-skills
```

Use information about monitor availability to distinguish "no evidence" from "no bottleneck."
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

1. Start at the CSB repository root and identify complete runs under `results/`.
2. Treat each basename as one CSB run only when all of these siblings exist: `<name>/`, `<name>.json`, `<name>.html`, and `<name>.csv`. If one artifact is missing, report the run as incomplete and avoid mixing it into comparisons unless the user explicitly asks.
3. For every complete run, generate a separate first-pass evidence report. Prefix every analysis Markdown filename with the same run-style prefix used by the results basename: `benchmark_<systemname>...`. Prefer `{base}` so the Markdown filename starts with the exact complete run basename and cannot collide with another run:

```bash
python3 /etc/codex/skills/csb-analysis/scripts/csb_result_report.py results \
  --out 'results/{base}_csb-analysis.md' \
  --summary-out results/benchmark_scaling_summary.md
```

   - Sanitize names for filesystem safety: lowercase if helpful, replace spaces and slashes with `-`, and keep function names recognizable.
   - Include commit hashes, subjects, dates, touched files, a short description of each change, and why it may or may not affect the observed CSB degradation.
   - Link this artifact from the main benchmark analysis report.

4. For each generated run-prefixed report, inspect that run's highest-degradation parameter points and monitor files directly before moving to the next benchmark. Reset the analysis state between runs: recompute baselines, inflection points, monitor summaries, source-correlation candidates, linux-perf/performance-patterns classification, and hypotheses from that run's CSV and monitor artifacts only. When extracting symbols from saved `perf.data` files under `results/`, run offline perf readers with `sudo` so kernel symbols can be resolved, for example `sudo perf report --stdio -i <perf.data> --sort symbol,dso --percent-limit 0.5` and `sudo perf script -i <perf.data>`.
5. Ensure Linux source exists in `deps/linux`; this single tree is used for both tested-kernel source correlation and upstream comparison. If absent, clone Torvalds Linux before making source-code claims:

```bash
git clone https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git deps/linux
```

Identify the distribution and running kernel from the testing machine, not from the analysis host, using artifacts such as `sys-config/uname.txt`, `sys-config/os-release.txt`, `sys-config/kconfig.txt`, `/proc/version`, or remote commands when the host is reachable. Add a distribution remote to `deps/linux` when the kernel is distro/vendor patched, fetch all refs from that remote, and check out the branch/tag/commit that most closely matches the running kernel before source correlation. Prefer exact distro source first, then the nearest distro branch for the same kernel series, then Torvalds main only as an explicitly approximate fallback.

Suggested remote selection:

- Ubuntu/Debian packaged kernels: add the matching distro kernel git remote when available, otherwise record that package source is required.
- Fedora/RHEL/CentOS Stream: add the Fedora or CentOS Stream kernel dist-git/kernel-source remote that matches the release.
- SUSE/openSUSE: add the matching SUSE kernel source remote.
- Custom kernels such as `6.6.0+`: inspect `/proc/version`, kernel build metadata, local source paths, and any node-specific notes before deciding whether the closest branch is a local source tree, distro branch, stable branch, or Torvalds main.

Record the selected source provenance in every report: distribution, running kernel release, remote name and URL, checked-out branch/tag/commit, `git -C deps/linux rev-parse --short HEAD`, and whether `deps/linux` is dirty. If no matching distribution source can be found, say that source correlation is approximate and name the missing source package/remote.

6. Ensure the same `deps/linux` clone also has a Torvalds remote for upstream comparison. Name it `torvalds` unless that name already exists:

```bash
git -C deps/linux remote add torvalds https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git
git -C deps/linux fetch --all --tags
```

Compare the selected distribution/tested branch in `deps/linux` against `torvalds/main` from the same clone. Record both commit ids with `git -C deps/linux rev-parse --short HEAD` and `git -C deps/linux rev-parse --short torvalds/master` or `torvalds/main`.

7. Apply linux-perf/performance-patterns refinement before choosing a patch direction: classify the bottleneck as CPU-bound, lock/cacheline-bound, scheduler/wakeup-bound, I/O-wait/device-bound, memory-management-bound, or unresolved; then record which named performance patterns match or do not match. If a fresh perf run would resolve the classification or validate a patch hypothesis, try to set `perf_event_paranoid=-1` with sudo, check/remount tracefs for tracepoint events, and run the smallest useful CSB/perf profile at the relevant baseline/peak/cliff points.
8. Correlate hot symbols/callers to source in the checked-out distribution/tested branch of `deps/linux` with `rg`, `git grep`, and architecture-specific paths. Prefer exact symbol definitions before making patch proposals. Use performance-patterns detail files to choose the correct source structure to inspect, such as lock variables, counters, wait queues, flush queues, shared structs, or hot loops.
9. For every proposed patch direction or discovered hot kernel path, compare the selected distribution/tested branch in `deps/linux` against Torvalds main in the same clone. Use targeted commands such as `git -C deps/linux log HEAD..torvalds/master -- <path>`, `git -C deps/linux log HEAD..torvalds/main -- <path>`, `git -C deps/linux diff HEAD..torvalds/master -- <path>`, `git -C deps/linux show torvalds/master:<path>`, and symbol searches to identify upstream changes relevant to the hot function, lock, cacheline, syscall, filesystem, network, scheduler, memory-management, or architecture path. Do not treat unrelated churn as an improvement; require a plausible connection to the measured bottleneck and to the linux-perf/performance-patterns classification.
10. If Torvalds main appears to improve a hot path or subsume a proposed patch, describe what changed upstream, why it may improve the benchmarked scaling behavior, and whether a backport to the selected distribution/tested branch would likely help. Include the expected backport shape: commits to inspect/cherry-pick, files/functions touched, minimal pseudo-diff or adaptation plan, dependencies, conflicts, semantic risks, and CSB rerun matrix. If Torvalds main does not contain a relevant improvement, say so and keep the original patch proposal clearly separate.
11. Produce one detailed Markdown document per complete run unless the user explicitly asks for a cross-run synthesis. Both Markdown result files for a run must start with the same `benchmark_<systemname>` prefix taken from the run filename, and should normally start with the full run basename. For example: `results/benchmark_A2302940388_bm_min_mysql_recvfrom_sendto_0_0_20260609_121620_729848_analysis.md` and `results/benchmark_A2302940388_bm_min_mysql_recvfrom_sendto_0_0_20260609_121620_729848_csb-analysis.md`. Do not generate HTML by default. If the user requests HTML, render the Markdown with Python-Markdown and enable table support:

```bash
python3 -m markdown -x tables -x extra results/<analysis-file>.md > results/<analysis-file>.html
```

For "all results", create independent per-run documents first; then add or update the separate cross-run synthesis, and keep cross-run conclusions explicitly separate from per-run findings.

12. The cross-run summary must collect the essential many-core degradation information from all analyzed runs, estimate the potential for kernel scaling improvement, and rank tests by confidence that a proposed kernel-scaling patch or upstream backport would improve large many-core scaling. Treat the ranking as triage: it should combine benchmark degradation, success/latency movement, monitor evidence strength, linux-perf/performance-patterns classification, source-correlation plausibility, and upstream-comparison strength. Do not claim a patch or backport will help from degradation alone.
13. The cross-run summary and every detailed run report must use local Markdown links for files they reference whenever practical. In particular:
   - Link each run's original result HTML, e.g. `[result html](benchmark_<...>.html)`.
   - Link each generated detailed analysis Markdown from the summary, e.g. `[analysis markdown](benchmark_<...>_csb-analysis.md)`.
   - Link generated analysis HTML only when HTML output was requested and the file exists.
   - Link Linux source files referenced in source-correlation tables or notes, using paths relative to the report location, e.g. `[fs/sync.c:180](../deps/linux/fs/sync.c#L180)`.
   - When discussing Torvalds-main improvements, link the checked-out local path in `deps/linux` and name the compared Torvalds ref/commit in text; do not link to `deps/linux-upstream`.
   - Prefer linked paths over plain backticked paths for navigational targets; keep non-file identifiers such as symbols, benchmark names, and execution types in backticks.
14. When the user asks to prepare kernel patches, create per-run patch-series artifacts instead of editing the benchmark evidence reports in place. For each run directory, create a descriptive folder such as `patch-series-ext4-fsync-flush-coalescing/` or `patch-series-vfs-namei-negative-lookup-cache/`. Put the generated patch file and its safety/implications documentation in that folder, and update a global index such as `results/kernel_patch_preparation_summary.md`.
15. After generating reports or patch-series documents, run local-link sanity checks. Resolve every Markdown link from the file that contains it; missing original result HTML or optionally generated analysis HTML must be marked as missing rather than linked. Nested patch-series documents need deeper relative paths for kernel source links, e.g. from `results/<run>/patch-series-*/` use `[fs/sync.c:180](../../../deps/linux/fs/sync.c#L180)`, not the shallower summary/report path.

## Runner Comparison Reports

Use `bm-runner/analyze.py` when the user wants a compact comparison report across CSB result CSVs, especially kernel-vs-kernel throughput, success-rate, and scaling plots. Treat it as a convenience post-processor, not as a replacement for the per-run evidence workflow above.

The script:

- recursively discovers `.csv` files under the supplied folders;
- expects default CSB benchmark result CSV columns such as `algo_name`, `throughput_min`, `container_cnt`, `univ_succ_percent`, `kernel`, `execution_type`, `hostname`, and `nb_threads`;
- groups by benchmark, execution type, hostname, kernel, and thread count;
- averages throughput and success percent per `container_cnt`;
- computes `linearity` as throughput relative to the smallest container count in the same group;
- writes `analysis-results-<timestamp>/` with combined `results.csv`, `results.md`, `results.html`, per-benchmark text tables, PNG plots, and `linearity.md`.

Prefer running it from `bm-runner/` or with the repo virtualenv so local imports resolve:

```bash
cd bm-runner
TMPDIR=/tmp/csb-analyze MPLCONFIGDIR=/tmp/csb-mpl ../venv/bin/python analyze.py <csv-folder> [<csv-folder> ...]
```

Before using it, avoid these known traps:

- Do not point it at a full `results/` tree unless you first filter/copy only top-level benchmark result CSVs. It recursively picks up monitor CSVs such as `lock-contention.csv` and can crash with missing columns like `algo_name`.
- Ensure `tabulate` is installed, because pandas `to_markdown()` requires it and `requirements.txt` may not list it.
- If no valid benchmark CSVs remain, expect `pd.concat()` to fail; report this as "no valid CSB benchmark result CSVs" instead of treating it as an analysis result.
- Do not interpret its `linearity` column as scaling efficiency unless verified. As implemented it is speedup relative to the smallest container count, not `throughput(N) / (throughput(1) * N)`.
- Keep `noise`, `initial_size`, and other omitted dimensions in mind. The script currently groups by `algo_name`, `execution_type`, `hostname`, `kernel`, and `nb_threads`; if other dimensions vary, prepare separate input folders or analyze manually.
- Guard against zero baseline throughput before relying on linearity output.

## Evidence Rules

- Use CSV throughput/latency/success columns as the primary scaling signal.
- Compare by `execution_type`, `container_cnt`, `nb_threads`, `noise`, and `initial_size`; do not collapse dimensions unless they are constant.
- Compute degradation against the smallest process/container count for the same execution type and benchmark dimensions.
- Recompute baselines and degradation independently for each complete run; never carry baseline values, missing-monitor assumptions, hot-symbol rankings, or bottleneck hypotheses from one benchmark/run into another.
- Use monitor data as explanatory evidence, not as a replacement for benchmark output.
- Call out missing monitors, empty files, failed monitor commands, and partial runs.
- When perf, c2c, lock-stat, tracepoints, or bpftrace would materially change confidence, try to enable the needed host permission first (`perf_event_paranoid=-1` via sudo for perf, and readable/remounted tracefs for tracepoint/tracing events), then run a useful focused benchmark/profile to verify the hypothesis. If permission is blocked, preserve that as an evidence limitation.
- Keep native process and container results separate unless drawing an explicit overhead comparison.
- Avoid claiming a kernel root cause from one signal alone. Require at least a benchmark inflection plus a matching monitor signal plus plausible source-code path.
- Use linux-perf/performance-patterns as evidence multipliers, not as substitutes for CSB data. A named pattern requires matching profile/source evidence; if the skill mostly rules out a pattern, record that negative evidence.
- In cross-run summaries, rank patch-investigation confidence separately from observed degradation. A severe throughput cliff with missing monitor/source evidence is a high degradation result, but not a high-confidence patch target yet.

## Monitor Triage

Read [references/monitor-source-map.md](references/monitor-source-map.md) when correlating monitor files to Linux subsystems and patch candidates.

Prioritize:

- `perf.log`, `perf.err`, `perf.data`: cycles, instructions, context switches, task-clock, stalled cycles, and hot kernel symbols. Use `sudo perf report/script -i <perf.data>` for saved result captures so kernel symbols are available; if sudo is denied or unavailable, report that kernel symbol extraction is permission-limited.
- Tracefs-backed perf events: before interpreting missing block/sched/syscall tracepoint data as "no signal", verify tracefs is mounted and readable (`/sys/kernel/tracing` or `/sys/kernel/debug/tracing`) and that `perf list 'block:*' 'sched:*' 'syscalls:*'` can see the events. If not, try the tracefs remount protocol above or report the monitor as tracefs-permission-limited.
- `lock-contention.csv`, `perf-lock.log`: contended lock sites, total wait, average wait, caller, and lock class.
- `mpstat.json`: system time, iowait, softirq, interrupts, RCU, scheduler activity, and idle collapse.
- `iostat*.json`, `iostat*.log`, `iostat*.txt`: device utilization, queue depth, await, service time, and throughput.
- Arm SPE captures: memory latency, cache/TLB misses, branch behavior, and load/store source attribution.
- `bpftrace*`: syscall, tracepoint, kprobe, lock, scheduler, block, or network aggregations. Read script text as part of interpreting the output.
- linux-perf artifacts and concepts: `perf stat` IPC/cache/branch/context-switch counters, dual-profile baseline-vs-cliff comparisons, `perf c2c` HITM tables, `perf annotate` instruction clusters, and permission/debug-symbol limitations.
- performance-patterns outputs: pattern matches/non-matches such as TTAS spinlock, false sharing, per-CPU stats, mutex-to-rwlock, CV/futex thundering herd, SIMD/narrow-vector patterns, missing `restrict`, missing `vzeroupper`, fast CRC32C, library upgrade, or "outside known CPU/cache-line catalog".

## Report Shape

Use this structure for each benchmark:

- Run identity: basename, system name, benchmark name, timestamp, kernel, architecture, CPUs, cgroup mode, config summary.
- Scaling result: table of process/container counts, throughput, success percent, latency, CPU/sys/iowait, and degradation from baseline.
- Inflection points: where throughput stops scaling, success drops, latency jumps, idle falls, or kernel time grows.
- Monitor evidence: summarize top perf symbols, lock callers, mpstat/iostat pressure, SPE/bpftrace observations, and failed/missing monitors.
- linux-perf refinement: summarize scaling factors, marginal gains, dual-profile deltas, hardware counters, c2c/cacheline evidence, annotate findings, and any perf permission/debug-symbol limits that affect confidence.
- performance-patterns classification: list matching patterns, explicitly rule out misleading patterns, and connect any match to the candidate kernel resolution strategy.
- Source correlation: map symbols/callers to `deps/linux` files/functions, explain relevant code paths, and cite the search method.
- Upstream comparison: map the same hot files/functions from the selected distribution/tested branch in `deps/linux` to the chosen Torvalds ref in the same clone, summarize relevant upstream commits or diffs, and state whether Torvalds main already changes the measured bottleneck path.
- Navigation links: locally link referenced original result HTML, generated analysis Markdown, optional generated analysis HTML when requested, and Linux source files/line anchors so readers can move directly from summaries to detailed evidence and source.
- Hypothesis: explain the likely bottleneck and confidence level.
- Patch/backport proposal: state concrete kernel change direction or upstream backport direction, affected files/functions, expected benefit, risks, validation plan, and a minimal benchmark rerun matrix.
- Cross-run summary: table of all analyzed runs ranked by many-core degradation, monitor evidence, potential kernel scaling improvement, upstream improvement/backport opportunity, and confidence that a proposed patch or backport would improve large many-core scaling; include short per-run notes and caveats.

## Result Identity
- run:
- benchmark:
- kernel:
- host/architecture:
- result artifacts:

## Throughput Degradation
In benchmark `<name>` we observe that throughput starts dropping when `<execution-unit>` is >= `<Y>`.

- target subsystem and maintainers if known from `scripts/get_maintainer.pl`;
- code path and lock/data structure involved;
- linux-perf/performance-patterns classification and why the chosen patch shape follows from it;
- why many-core scaling degrades;
- upstream status from Torvalds main in the same `deps/linux` clone: relevant commits/diffs if upstream improved the path, or a brief note that no relevant upstream improvement was found;
- backport recommendation when upstream is ahead: whether to cherry-pick, adapt a subset, or avoid backporting; expected conflicts/dependencies; and a minimal patch shape for the tested `deps/linux` tree;
- alternative mitigations considered;
- validation metrics from CSB that should improve;
- validation metrics from linux-perf/performance-patterns that should move, such as IPC, context switches, HITM, lock wait, physical flush count, wakeups, hot instruction clusters, or symbol deltas;
- regressions to watch, especially memory use, fairness, latency tail, ABI behavior, and architecture-specific behavior.

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

- run identity, benchmark name, and completeness;
- link to the local patch file;
- links to the detailed Markdown report, optional generated HTML report when requested, and original result HTML when present;
- link back to the cross-run summary;
- source-correlation links to `deps/linux` paths with correct relative paths from the patch-series folder;
- upstream-comparison notes naming the compared Torvalds ref/commit in `deps/linux`; link source paths through the local `deps/linux` checkout rather than `deps/linux-upstream`;
- why this patch was selected and why it is expected to be profitable;
- linux-perf/performance-patterns evidence used to select or reject this patch theme;
- what the patch changes at the subsystem/function level;
- whether the patch is a novel RFC change, a backport/adaptation of upstream work, or a combination;
- safety level and assumptions;
- implications for semantics, latency, throughput, memory, fairness, crash consistency, permissions, LSM/fsnotify/accounting, cgroups, and architecture-specific behavior as applicable;
- validation checklist and benchmark rerun matrix.

6. Add or update `results/kernel_patch_preparation_summary.md`. It should be a concise index of all per-run patch-series folders with columns for run, patch series, theme, degradation, confidence, detailed report link, and original result HTML link. Missing artifacts must be written as `missing`, not linked.

## Patch Validation And Sanity Checks

Before reporting patch preparation as complete:

- Count patch-series directories and ensure the count matches the intended run set.
- Count patch files and ensure each patch-series directory has exactly the expected patch file(s).
- Verify every patch-series folder has `README.md` and `SAFETY_IMPLICATIONS_AND_DESCRIPTION.md`.
- Check for stale shallow kernel-source links in nested patch docs:

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
- existence and relevance of upstream changes since v6.6;
- confidence that a kernel patch or backport would improve many-core scaling.

Do not rank patch opportunity from throughput loss alone.
