---
name: csb-analysis
description: "Use when analyzing CSB results in a results/ directory, especially per-run benchmark folders with matching .json/.html/.csv artifacts, monitor captures from perf, lock contention, Arm SPE, iostat, mpstat, bpftrace, linux-perf workflows, performance-patterns classification, or requests to explain process/container scaling degradation, correlate bottlenecks with Linux kernel source, compare distribution-kernel hot paths against Torvalds main using one deps/linux clone, or propose/backport kernel patch directions for many-core systems. For SSH/remote benchmark hosts or copied remote artifacts, use csb-remote alongside this skill."
---

# CSB Analysis

Analyze CSB result runs as separate experiments, then connect benchmark scaling behavior to monitor evidence and Linux kernel code. Use the base `csb` skill for runner/config mechanics; use this skill when the task is post-run performance analysis. When `results/` contains multiple complete benchmarks/runs, rerun the full analysis workflow for each one independently; do not reuse hypotheses, baselines, monitor conclusions, or source-correlation assumptions from another benchmark unless a later cross-run comparison is explicitly requested.

For SSH/remote benchmark hosts, also use `csb-remote`. Treat the remote as the tested machine: run perf readers, tracefs/perf permission checks, source checkout updates, package installs, object builds, and any fresh validation benchmarks on the remote unless the user explicitly asks for offline host-only analysis of already copied artifacts. Copy generated reports and supporting artifacts back to the controller under remote-specific result directories.

## Performance Skill Integration

Use `linux-perf` and `performance-patterns` whenever they are available. They are not optional decoration: use them to improve evidence triage, bottleneck classification, kernel-source correlation, patch/backport selection, and validation planning.

At the start of an analysis that uses perf, flamegraph, lock contention, cache-line contention, CPU scaling, or kernel optimization evidence:

1. If `linux-perf` is listed as an available skill, read its `SKILL.md` and the referenced flow/building-block files needed for this run. For CSB scaling cliffs, prefer Flow D/core-count scaling concepts, adapted from "cores" to CSB's process/container/thread count dimension when appropriate.
2. If `performance-patterns` is listed as an available skill, read its `SKILL.md`, then read `triggers/from-profile.md` when profile data exists or `triggers/from-source.md` when only source evidence exists. Read the specific `patterns/*.md` files for every plausible match before recommending a fix.
3. If either skill is not available in the session but `deps/intel-performance-skills/skills/<skill>/SKILL.md` exists, read and apply those local files as bundled reference material.
4. If the local `deps/intel-performance-skills` tree is missing and network access is permitted or approved, clone it before continuing:

```bash
git clone https://github.com/intel/intel-performance-skills.git deps/intel-performance-skills
```

If the clone is blocked by network/sandbox policy, continue the CSB analysis and explicitly state that linux-perf/performance-patterns refinement was unavailable.

Use these skills to add, when evidence allows:

- a linux-perf-style scaling table with score factors, marginal gains, and inflection points;
- a dual-profile or saved-profile delta between baseline/peak/cliff points;
- hardware-counter interpretation when `perf stat` data exists;
- cache-line/lock contention interpretation when `perf c2c`, lock contention, or HITM evidence exists;
- a performance-patterns classification table that names matching patterns and explicitly rules out tempting non-matches;
- a patch-direction mapping from measured pattern to resolution strategy, or a clear statement that the run is outside the known CPU/cache-line pattern catalog.

Do not force a pattern. If evidence shows I/O wait, scheduler sleep, device flush latency, external serialization, or missing monitor data rather than a CPU-bound pattern, say so and use linux-perf/performance-patterns mainly to rule out CPU-side fixes and to design the next measurement.

When running perf would materially improve or verify a hypothesis, actively try to enable full perf access instead of treating restricted perf as a final state:

```bash
cat /proc/sys/kernel/perf_event_paranoid
echo -1 | sudo tee /proc/sys/kernel/perf_event_paranoid
cat /proc/sys/kernel/perf_event_paranoid
```

For tracepoint-backed perf events, bpftrace, scheduler/block/syscall tracing, and lock/sched diagnostics that use tracefs, check and fix tracefs access too:

```bash
TRACEFS=/sys/kernel/tracing
test -d "$TRACEFS" || TRACEFS=/sys/kernel/debug/tracing
findmnt -T "$TRACEFS"
test -r "$TRACEFS/events" && test -x "$TRACEFS/events"
sudo mount -o remount,mode=755 "$TRACEFS"
test -r "$TRACEFS/events" && test -x "$TRACEFS/events"
perf list 'block:*' 'sched:*' 'syscalls:*' >/tmp/csb-perf-tracepoint-list.txt
```

If tracefs is not mounted, try `sudo mount -t tracefs nodev /sys/kernel/tracing` first. If sudo is approved and `perf_event_paranoid=-1` plus readable tracefs are in place, run an actually useful perf-backed benchmark/profile to test the hypothesis, not just a permission check. Keep it focused: baseline count, peak/plateau count, and cliff/largest count for the affected execution type are usually enough. If sudo is denied, unavailable, or policy blocks the change, state that perf/tracefs evidence is permission-limited and design the next validation command rather than overclaiming from partial data.

## Quick Workflow

1. Start at the CSB repository root and identify complete runs under `results/`.
2. Treat each basename as one CSB run only when all of these siblings exist: `<name>/`, `<name>.json`, `<name>.html`, and `<name>.csv`. If one artifact is missing, report the run as incomplete and avoid mixing it into comparisons unless the user explicitly asks.
3. For every complete run, generate a separate first-pass evidence report. Prefix every analysis Markdown filename with the same run-style prefix used by the results basename: `benchmark_<systemname>...`. Prefer `{base}` so the Markdown filename starts with the exact complete run basename and cannot collide with another run:

```bash
python3 /etc/codex/skills/csb-analysis/scripts/csb_result_report.py results \
  --out 'results/{base}_csb-analysis.md' \
  --summary-out results/benchmark_scaling_summary.md
```

The report helper writes one Markdown file per complete run when the `--out` path contains placeholders. It also writes a cross-run summary when `--summary-out` is set, and writes adjacent `.html` files for all Markdown reports by default.

4. For each generated run-prefixed report, inspect that run's highest-degradation parameter points and monitor files directly before moving to the next benchmark. Reset the analysis state between runs: recompute baselines, inflection points, monitor summaries, source-correlation candidates, linux-perf/performance-patterns classification, and hypotheses from that run's CSV and monitor artifacts only. When extracting symbols from saved `perf.data` files under `results/`, run offline perf readers with `sudo` so kernel symbols can be resolved, for example `sudo perf report --stdio -i <perf.data> --sort symbol,dso --percent-limit 0.5` and `sudo perf script -i <perf.data>`.
5. Ensure Linux source exists in `deps/linux`; this single tree is used for both tested-kernel source correlation and upstream comparison. If absent, clone Torvalds Linux before making source-code claims:

```bash
git clone https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git deps/linux
```

Identify the distribution and running kernel from the testing machine using artifacts such as `sys-config/uname.txt`, `sys-config/os-release.txt`, `sys-config/kconfig.txt`, `/proc/version`, or remote commands when the machine is reachable. For remote workflows, do this in the remote `deps/linux` tree following `csb-remote`, then copy source-provenance notes back with the reports. Add a distribution remote to `deps/linux` when the kernel is distro/vendor patched, fetch all refs from that remote, and check out the branch/tag/commit that most closely matches the running kernel before source correlation. Prefer exact distro source first, then the nearest distro branch for the same kernel series, then Torvalds main only as an explicitly approximate fallback.

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

Do not create or require `deps/linux-upstream`. Compare the selected distribution/tested branch in `deps/linux` against `torvalds/master` or `torvalds/main` from the same clone. Record both commit ids with `git -C deps/linux rev-parse --short HEAD` and `git -C deps/linux rev-parse --short torvalds/master` or `torvalds/main`.

7. Apply linux-perf/performance-patterns refinement before choosing a patch direction: classify the bottleneck as CPU-bound, lock/cacheline-bound, scheduler/wakeup-bound, I/O-wait/device-bound, memory-management-bound, or unresolved; then record which named performance patterns match or do not match. If a fresh perf run would resolve the classification or validate a patch hypothesis, try to set `perf_event_paranoid=-1` with sudo, check/remount tracefs for tracepoint events, and run the smallest useful CSB/perf profile at the relevant baseline/peak/cliff points.
8. Correlate hot symbols/callers to source in the checked-out distribution/tested branch of `deps/linux` with `rg`, `git grep`, and architecture-specific paths. Prefer exact symbol definitions before making patch proposals. Use performance-patterns detail files to choose the correct source structure to inspect, such as lock variables, counters, wait queues, flush queues, shared structs, or hot loops.
9. For every proposed patch direction or discovered hot kernel path, compare the selected distribution/tested branch in `deps/linux` against Torvalds main in the same clone. Use targeted commands such as `git -C deps/linux log HEAD..torvalds/master -- <path>`, `git -C deps/linux log HEAD..torvalds/main -- <path>`, `git -C deps/linux diff HEAD..torvalds/master -- <path>`, `git -C deps/linux show torvalds/master:<path>`, and symbol searches to identify upstream changes relevant to the hot function, lock, cacheline, syscall, filesystem, network, scheduler, memory-management, or architecture path. Do not treat unrelated churn as an improvement; require a plausible connection to the measured bottleneck and to the linux-perf/performance-patterns classification.
10. If Torvalds main appears to improve a hot path or subsume a proposed patch, describe what changed upstream, why it may improve the benchmarked scaling behavior, and whether a backport to the selected distribution/tested branch would likely help. Include the expected backport shape: commits to inspect/cherry-pick, files/functions touched, minimal pseudo-diff or adaptation plan, dependencies, conflicts, semantic risks, and CSB rerun matrix. If Torvalds main does not contain a relevant improvement, say so and keep the original patch proposal clearly separate.
11. Produce one detailed document per complete run unless the user explicitly asks for a cross-run synthesis. Both Markdown result files for a run must start with the same `benchmark_<systemname>` prefix taken from the run filename, and should normally start with the full run basename. For example: `results/benchmark_A2302940388_bm_min_mysql_recvfrom_sendto_0_0_20260609_121620_729848_analysis.md` and `results/benchmark_A2302940388_bm_min_mysql_recvfrom_sendto_0_0_20260609_121620_729848_csb-analysis.md`. For every analysis Markdown file, generate an adjacent HTML file with the same stem:

```bash
python3 /etc/codex/skills/csb-analysis/scripts/md_to_html.py results/<analysis-file>.md
```

For "all results", create independent per-run documents first; then add or update the separate cross-run synthesis, and keep cross-run conclusions explicitly separate from per-run findings.

12. The cross-run summary must collect the essential many-core degradation information from all analyzed runs, estimate the potential for kernel scaling improvement, and rank tests by confidence that a proposed kernel-scaling patch or upstream backport would improve large many-core scaling. Treat the ranking as triage: it should combine benchmark degradation, success/latency movement, monitor evidence strength, linux-perf/performance-patterns classification, source-correlation plausibility, and upstream-comparison strength. Do not claim a patch or backport will help from degradation alone.
13. The cross-run summary and every detailed run report must use local Markdown links for files they reference whenever practical. In particular:
   - Link each run's original result HTML, e.g. `[result html](benchmark_<...>.html)`.
   - Link each generated detailed analysis HTML from the summary, e.g. `[analysis html](benchmark_<...>_csb-analysis.html)`.
   - Link Linux source files referenced in source-correlation tables or notes, using paths relative to the report location, e.g. `[fs/sync.c:180](../deps/linux/fs/sync.c#L180)`.
   - When discussing Torvalds-main improvements, link the checked-out local path in `deps/linux` and name the compared Torvalds ref/commit in text; do not link to `deps/linux-upstream`.
   - Prefer linked paths over plain backticked paths for navigational targets; keep non-file identifiers such as symbols, benchmark names, and execution types in backticks.
14. When the user asks to prepare kernel patches, create per-run patch-series artifacts instead of editing the benchmark evidence reports in place. For each run directory, create a descriptive folder such as `patch-series-ext4-fsync-flush-coalescing/` or `patch-series-vfs-namei-negative-lookup-cache/`. Put the generated patch file and its safety/implications documentation in that folder, and update a global index such as `results/kernel_patch_preparation_summary.md`.
15. After generating reports or patch-series documents, run local-link sanity checks. Resolve every Markdown link from the file that contains it; missing result HTML or analysis HTML must be marked as missing rather than linked. Nested patch-series documents need deeper relative paths for kernel source links, e.g. from `results/<run>/patch-series-*/` use `[fs/sync.c:180](../../../deps/linux/fs/sync.c#L180)`, not the shallower summary/report path.

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

Write the final analysis as a technical document, not a raw dump:

- Run identity: basename, system name, benchmark name, timestamp, kernel, architecture, CPUs, cgroup mode, config summary.
- Scaling result: table of process/container counts, throughput, success percent, latency, CPU/sys/iowait, and degradation from baseline.
- Inflection points: where throughput stops scaling, success drops, latency jumps, idle falls, or kernel time grows.
- Monitor evidence: summarize top perf symbols, lock callers, mpstat/iostat pressure, SPE/bpftrace observations, and failed/missing monitors.
- linux-perf refinement: summarize scaling factors, marginal gains, dual-profile deltas, hardware counters, c2c/cacheline evidence, annotate findings, and any perf permission/debug-symbol limits that affect confidence.
- performance-patterns classification: list matching patterns, explicitly rule out misleading patterns, and connect any match to the candidate kernel resolution strategy.
- Source correlation: map symbols/callers to `deps/linux` files/functions, explain relevant code paths, and cite the search method.
- Upstream comparison: map the same hot files/functions from the selected distribution/tested branch in `deps/linux` to the chosen Torvalds ref in the same clone, summarize relevant upstream commits or diffs, and state whether Torvalds main already changes the measured bottleneck path.
- Navigation links: locally link referenced original result HTML, generated analysis HTML, and Linux source files/line anchors so readers can move directly from summaries to detailed evidence and source.
- Hypothesis: explain the likely bottleneck and confidence level.
- Patch/backport proposal: state concrete kernel change direction or upstream backport direction, affected files/functions, expected benefit, risks, validation plan, and a minimal benchmark rerun matrix.
- Cross-run summary: table of all analyzed runs ranked by many-core degradation, monitor evidence, potential kernel scaling improvement, upstream improvement/backport opportunity, and confidence that a proposed patch or backport would improve large many-core scaling; include short per-run notes and caveats.

## Patch Proposal Discipline

The patch proposal can be a design note or pseudo-diff unless the user asks for an actual patch. Keep it tied to observed evidence. Include:

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

## Patch-Series Preparation

Use this section when the user asks to prepare the most profitable kernel patches, patch series, patch files, or per-run patch folders from analyzed CSB results.

1. Start from the completed per-run analysis reports and the cross-run summary. Identify every complete run under `results/`, and also list incomplete run directories separately so they do not silently disappear.
2. Select the most profitable patch theme per run using evidence, not degradation alone. Prefer high-confidence themes where throughput collapse, latency/success movement, monitor data, and source correlation point to the same kernel subsystem. Lower-confidence or incomplete runs may receive diagnostic/RFC patches, but the documentation must say so plainly.
3. Create one patch-series directory per run:

```text
results/<run>/patch-series-<short-change-name>/
```

Name the directory after the proposed change rather than a generic label. Examples:

- `patch-series-ext4-fsync-flush-coalescing`
- `patch-series-ext4-fallocate-preallocation-fastpath`
- `patch-series-vfs-may-access-fastperm`
- `patch-series-vfs-namei-negative-lookup-cache`
- `patch-series-vfs-read-write-iter-fastpath`
- `patch-series-net-socket-batching`

4. Put the patch file in that folder with a reviewable subject-based name, for example:

```text
0001-rfc-ext4-add-opt-in-fsync-flush-coalescing.patch
0001-rfc-ext4-fast-preallocated-keep-size-fallocate.patch
0001-vfs-skip-generic-permission-for-may-access.patch
```

If the implementation is not production-ready, mark the patch subject and filename as `rfc`. Do not apply generated RFC patches to `deps/linux` unless the user explicitly asks.

5. Add both `SAFETY_IMPLICATIONS_AND_DESCRIPTION.md` and `README.md` to the patch-series folder. The two files may have the same content for easy navigation. Each document must include:

- run identity, benchmark name, and completeness;
- link to the local patch file;
- links to the detailed Markdown/HTML report and original result HTML when present;
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
rg -n '\]\(\.\./deps/linux/' results -g 'SAFETY_IMPLICATIONS_AND_DESCRIPTION.md' -g 'README.md'
```

This should return no matches for nested patch-series documents.

- Resolve Markdown links from their containing file. A simple local resolver should strip anchors such as `#L180`, ignore external URLs, and report missing local files. The expected result for generated patch-preparation docs is `missing_links=0`.
- For incomplete runs, verify that documentation explicitly says which artifacts are missing and does not contain broken links to absent `.html` reports.
- Do not claim that a generated RFC patch is upstreamable or production-safe until it has been applied to a clean kernel tree, built, checked with `scripts/checkpatch.pl`, tested with relevant subsystem tests, and rerun against the selected CSB counts.
