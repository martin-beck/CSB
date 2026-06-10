---
name: csb-analysis
description: "Use when analyzing CSB results in a results/ directory, especially per-run benchmark folders with matching .json/.html/.csv artifacts, monitor captures from perf, lock contention, Arm SPE, iostat, mpstat, or bpftrace, and requests to explain process/container scaling degradation, correlate bottlenecks with Linux kernel source, or propose kernel patch directions for many-core systems."
---

# CSB Analysis

Analyze CSB result runs as separate experiments, then connect benchmark scaling behavior to monitor evidence and Linux kernel code. Use the base `csb` skill for runner/config mechanics; use this skill when the task is post-run performance analysis. When `results/` contains multiple complete benchmarks/runs, rerun the full analysis workflow for each one independently; do not reuse hypotheses, baselines, monitor conclusions, or source-correlation assumptions from another benchmark unless a later cross-run comparison is explicitly requested.

## Quick Workflow

1. Start at the CSB repository root and identify complete runs under `results/`.
2. Treat each basename as one CSB run only when these siblings exist: `<name>/`, `<name>.json`, `<name>.html`, and `<name>.csv`. If one artifact is missing, report the run as incomplete and avoid mixing it into comparisons unless the user explicitly asks.
3. For every complete run, generate a separate first-pass evidence report. Prefix every analysis Markdown filename with the same run-style prefix used by the results basename: `benchmark_<systemname>...`. Prefer `{base}` so the Markdown filename starts with the exact complete run basename and cannot collide with another run:

```bash
python3 /etc/codex/skills/csb-analysis/scripts/csb_result_report.py results --out 'results/{base}_csb-analysis.md'
```

The report helper writes one Markdown file per complete run when the `--out` path contains placeholders.
It also writes an adjacent `.html` file for each Markdown report by default.

4. For each generated run-prefixed report, inspect that run's highest-degradation parameter points and monitor files directly before moving to the next benchmark. Reset the analysis state between runs: recompute baselines, inflection points, monitor summaries, source-correlation candidates, and hypotheses from that run's CSV and monitor artifacts only.
5. Ensure Linux source exists in `deps/linux`; if absent, clone it before making source-code claims:

```bash
git clone --depth 1 https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git deps/linux
```

If the running kernel is distro-patched, prefer matching sources when available; otherwise state that `deps/linux` is upstream reference code and source-line correlation may be approximate.

6. Correlate hot symbols/callers to source with `rg`, `git grep`, and architecture-specific paths. Prefer exact symbol definitions before making patch proposals.
7. Produce one detailed document per complete run unless the user explicitly asks for a cross-run synthesis. Both Markdown result files for a run must start with the same `benchmark_<systemname>` prefix taken from the run filename, and should normally start with the full run basename. For example: `results/benchmark_A2302940388_bm_min_mysql_recvfrom_sendto_0_0_20260609_121620_729848_analysis.md` and `results/benchmark_A2302940388_bm_min_mysql_recvfrom_sendto_0_0_20260609_121620_729848_csb-analysis.md`. For every analysis Markdown file, generate an adjacent HTML file with the same stem:

```bash
python3 /etc/codex/skills/csb-analysis/scripts/md_to_html.py results/<analysis-file>.md
```

For "all results", create independent per-run documents first; only then add a separate cross-run synthesis, and keep cross-run conclusions explicitly separate from per-run findings.

## Evidence Rules

- Use CSV throughput/latency/success columns as the primary scaling signal.
- Compare by `execution_type`, `container_cnt`, `nb_threads`, `noise`, and `initial_size`; do not collapse dimensions unless they are constant.
- Compute degradation against the smallest process/container count for the same execution type and benchmark dimensions.
- Recompute baselines and degradation independently for each complete run; never carry baseline values, missing-monitor assumptions, hot-symbol rankings, or bottleneck hypotheses from one benchmark/run into another.
- Use monitor data as explanatory evidence, not as a replacement for benchmark output.
- Call out missing monitors, empty files, failed monitor commands, and partial runs.
- Keep native process and container results separate unless drawing an explicit overhead comparison.
- Avoid claiming a kernel root cause from one signal alone. Require at least a benchmark inflection plus a matching monitor signal plus plausible source-code path.

## Monitor Triage

Read [references/monitor-source-map.md](references/monitor-source-map.md) when correlating monitor files to Linux subsystems and patch candidates.

Prioritize:

- `perf.log`, `perf.err`, `perf.data`: cycles, instructions, context switches, task-clock, stalled cycles, and hot kernel symbols.
- `lock-contention.csv`, `perf-lock.log`: contended lock sites, total wait, average wait, caller, and lock class.
- `mpstat.json`: system time, iowait, softirq, interrupts, RCU, scheduler activity, and idle collapse.
- `iostat*.json`, `iostat*.log`, `iostat*.txt`: device utilization, queue depth, await, service time, and throughput.
- Arm SPE captures: memory latency, cache/TLB misses, branch behavior, and load/store source attribution.
- `bpftrace*`: syscall, tracepoint, kprobe, lock, scheduler, block, or network aggregations. Read script text as part of interpreting the output.

## Report Shape

Write the final analysis as a technical document, not a raw dump:

- Run identity: basename, system name, benchmark name, timestamp, kernel, architecture, CPUs, cgroup mode, config summary.
- Scaling result: table of process/container counts, throughput, success percent, latency, CPU/sys/iowait, and degradation from baseline.
- Inflection points: where throughput stops scaling, success drops, latency jumps, idle falls, or kernel time grows.
- Monitor evidence: summarize top perf symbols, lock callers, mpstat/iostat pressure, SPE/bpftrace observations, and failed/missing monitors.
- Source correlation: map symbols/callers to `deps/linux` files/functions, explain relevant code paths, and cite the search method.
- Hypothesis: explain the likely bottleneck and confidence level.
- Patch proposal: state concrete kernel change direction, affected files/functions, expected benefit, risks, validation plan, and a minimal benchmark rerun matrix.

## Patch Proposal Discipline

The patch proposal can be a design note or pseudo-diff unless the user asks for an actual patch. Keep it tied to observed evidence. Include:

- target subsystem and maintainers if known from `scripts/get_maintainer.pl`;
- code path and lock/data structure involved;
- why many-core scaling degrades;
- alternative mitigations considered;
- validation metrics from CSB that should improve;
- regressions to watch, especially memory use, fairness, latency tail, ABI behavior, and architecture-specific behavior.
