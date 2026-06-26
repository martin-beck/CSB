---
name: csb-remote
description: "Use when CSB work runs on one or more SSH benchmark hosts while the current host acts as controller: remote setup, benchmark/refine/analysis commands, monitor permissions, reconnects, multi-host coordination, and copying results/reports/configs/artifacts back."
---

# CSB Remote

This is a remote-execution overlay for CSB work. Apply the relevant CSB skill or docs normally, but run benchmark-machine-dependent steps on the SSH benchmark host and keep kernel-source work on the controller.

## Compose With

- `csb`: benchmark setup, config selection, monitors, and campaign execution.
- `csb-analysis`: result analysis, perf/flamegraph/lock evidence, controller-side source correlation, patch artifacts.
- `csb-refine`: iterative reruns, cleanup, monitor adaptation, conclusions, controller-side object-build testing.
- Project docs for stable CSB facts: `doc/bm-runner.md`, `doc/bm-config.md`, `doc/development.md`, plus app notes under `doc/bm-external/` and `doc/org-apps/`.

When those sources say "host", "machine", "testing machine", or "prepare the environment", read it as the remote benchmark host only for benchmark runtime, monitor, permission, package, cgroup, topology, and cleanup work. Keep all kernel source trees, kernel git remotes, source correlation, patch-history searches, patch artifacts, and object-build tests on the controller.

## SSH Access

Verify SSH with a non-destructive command before setup or benchmarks:

```bash
ssh <remote> 'hostname'
```

If access fails, help diagnose the SSH target, username, key, host key, jump host, or `~/.ssh/config` entry. Do not start setup, package installation, or CSB runs until the remote host is reachable.

## Remote Invariants

- Treat the remote as source of truth for benchmark output, running-kernel facts, topology, cgroups, runtimes, monitor availability, and permissions.
- Run runtime checks, package installs, benchmark commands, monitor captures, and cleanup on the remote.
- Keep kernel source under the controller checkout. Any added kernel git remote, branch, tag, commit, dirty-state note, or comparison ref used by `csb-analysis` or `csb-refine` must match the remote host's running kernel, not the controller's kernel.
- Do not infer remote capability from the controller. Verify Docker/runc/youki, perf, tracefs, bpftrace, sysstat, NICs, cgroups, and running-kernel identity on the remote.
- For multiple remote hosts, prefix tmux sessions, result groups, temp configs, and copied directories with `csb-remote_<remote>_`.
- Do not kill, rename, or reuse unrelated user tmux sessions.
- If SSH drops, reconnect and inspect remote sessions/processes before restarting or cleaning up.

## Minimal Inventory

Record this before running CSB and include it in reports:

```bash
ssh <remote> 'hostname; pwd; uname -a; cat /etc/os-release 2>/dev/null || true; nproc; lscpu | sed -n "1,80p"'
ssh <remote> 'command -v git python3 sudo perf bpftrace docker runc youki mpstat iostat || true'
ssh <remote> 'test -d /path/to/csb && git -C /path/to/csb status --short || true'
```

Also track: SSH target, remote CSB checkout path, result group/root, remote running-kernel identity, controller kernel-source path/ref used for that host, runtime and monitor permissions, and any node-specific cleanup quirks.

## Execution Pattern

Use SSH from the controller and execute from the remote CSB checkout:

```bash
ssh <remote> 'cd /path/to/csb && CSB_RESULTS_GROUP=<remote>_<group> scripts/run-single.sh config/<file>.json'
```

Always use a remote `tmux` or `systemd-run` session:

```bash
ssh <remote> 'cd /path/to/csb && tmux new-session -d -s csb-remote_<remote>_<name> "CSB_RESULTS_GROUP=<group> scripts/run-single.sh config/<file>.json 2>&1 | tee results/<group>.log"'
ssh <remote> 'tmux capture-pane -pt csb-remote_<remote>_<name> -S -200'
```

Before reruns, use the cleanup guidance from the active CSB skill on the remote only. Clean only artifacts that belong to the prior CSB sweep, then re-check and record the cleanup summary.

## Copy-Back Layout

At the end of each task, copy final CSB result directories and task-produced reports/configs/logs to the controller. Include monitor or patch artifacts only when they were generated remotely and are needed for analysis or review:

```text
results/remote/<remote>/<task-or-group>/
  results/          # copied remote results/<group> or selected run dirs
  reports/          # summary/detailed/cross-run reports
  configs/          # configs used for the remote runs
  monitors/         # generated probes or profiler artifacts needed for analysis
  patches/          # RFC patches and patch support docs, if any
  logs/             # driver logs, tmux captures, install/setup notes
  inventory/        # uname, lscpu, os-release, tool versions, git refs
```

Use `rsync -a --info=progress2` or `scp -r`. For large `perf.data`, flamegraphs, or traces, copy only what is needed unless the user asks for full raw data. Preserve remote filenames/run basenames.

## Reporting

Reports should state which work ran remotely vs on the controller; remote hostname/kernel/CPU/cgroups/runtime/monitors; controller kernel-source path/ref chosen for that remote host; cleanup performed; copied-back paths; remote installs or permission changes; reconnects or failed probes; and any raw data intentionally left remote.

When the user asks for "all reports/results/configs copied back", verify the controller copy has the expected Markdown/HTML/CSV/JSON/result directories before finishing.
