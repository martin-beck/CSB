---
name: csb-remote
description: "Use when CSB work runs on one or more SSH benchmark hosts while the current host acts as controller: remote setup, benchmark/refine/analysis/dev commands, monitor permissions, reconnects, multi-host coordination, and copying results/reports/configs/artifacts back."
---

# CSB Remote

This is a remote-execution overlay for CSB work. Apply the relevant CSB skill or docs normally, but run machine-dependent steps on the SSH benchmark host and copy final artifacts back to the controller.

## Compose With

- `csb`: benchmark setup, configs, monitors, and campaign execution.
- `csb-analysis`: result analysis, source correlation, perf/flamegraph/lock evidence, patch artifacts.
- `csb-refine`: iterative reruns, cleanup, monitor adaptation, conclusions, object-build testing.
- Project docs for stable CSB facts: `doc/bm-runner.md`, `doc/bm-config.md`, `doc/development.md`, plus app notes under `doc/bm-external/` and `doc/org-apps/`.

When those sources say "host", "machine", "local command", "testing machine", or "prepare the environment", read it as the remote benchmark host for remote work. Keep controller-only work limited to orchestration, skill/template editing, copied artifacts, and cross-remote summaries unless the user asks otherwise.

## Remote Invariants

- Treat the remote as source of truth for benchmark output, kernel facts, topology, cgroups, runtimes, monitor availability, permissions, and source trees.
- Run all runtime checks, package installs, benchmark commands, monitor captures, cleanup, artifact-dependent analysis, and kernel builds on the remote.
- Do not infer remote capability from the controller. Verify Docker/runc/youki, perf, tracefs, bpftrace, sysstat, NICs, cgroups, and kernel source on the remote.
- For multiple remotes, prefix tmux sessions, result groups, temp configs, and copied directories with the remote name.
- If SSH drops, reconnect and inspect remote sessions/processes before restarting or cleaning up.

## Minimal Inventory

Record this before running CSB and include it in reports:

```bash
ssh <remote> 'hostname; pwd; uname -a; cat /etc/os-release 2>/dev/null || true; nproc; lscpu | sed -n "1,80p"'
ssh <remote> 'command -v git python3 sudo perf bpftrace docker runc youki mpstat iostat || true'
ssh <remote> 'test -d /path/to/csb && git -C /path/to/csb status --short || true'
```

Also track: SSH target, remote CSB checkout path, result group/root, kernel/source path, runtime and monitor permissions, and any node-specific cleanup quirks.

## Execution Pattern

Use SSH from the controller and execute from the remote CSB checkout:

```bash
ssh <remote> 'cd /path/to/csb && CSB_RESULTS_GROUP=<remote>_<group> scripts/run-single.sh config/<file>.json'
```

For long runs, prefer a remote `tmux` or `systemd-run` session:

```bash
ssh <remote> 'cd /path/to/csb && tmux new-session -d -s csb_<remote>_<name> "CSB_RESULTS_GROUP=<group> scripts/run-single.sh config/<file>.json 2>&1 | tee results/<group>.log"'
ssh <remote> 'tmux capture-pane -pt csb_<remote>_<name> -S -200'
```

Before reruns, use the cleanup guidance from `csb-refine` on the remote only. Clean stale processes, runtime state, monitors, start barriers, and scratch artifacts that belong to the prior CSB sweep; re-check and record the cleanup summary.

## Copy-Back Layout

At the end of each task, copy final results, reports, configs, generated probes/scripts, logs, and patch artifacts to:

```text
results/remote/<remote>/<task-or-group>/
  results/          # copied remote results/<group> or selected run dirs
  reports/          # summary/detailed/cross-run reports
  configs/          # configs used for the remote runs
  monitors/         # generated bpftrace programs, perf scripts, helper probes
  patches/          # RFC patches and patch support docs, if any
  logs/             # driver logs, tmux captures, install/setup notes
  inventory/        # uname, lscpu, os-release, tool versions, git refs
```

Use `rsync -a --info=progress2` or `scp -r`. For large `perf.data`, flamegraphs, or traces, copy only what is needed unless the user asks for full raw data. Preserve remote filenames/run basenames.

## Reporting

Reports should state which work ran remotely vs on the controller; hostname/kernel/CPU/cgroups/runtime/monitors/source commits; cleanup performed; copied-back paths; remote installs or permission changes; reconnects or failed probes; and any raw data intentionally left remote.

When the user asks for "all reports/results/configs copied back", verify the controller copy has the expected Markdown/HTML/CSV/JSON/result directories before finishing.
