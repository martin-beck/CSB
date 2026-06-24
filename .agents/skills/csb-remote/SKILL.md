---
name: csb-remote
description: "Use when CSB work is executed on one or more remote benchmark machines over SSH while the current host acts as the AI/controller host: preparing remote CSB checkouts and dependencies, installing benchmark/monitor tooling, setting permissions, syncing host skills/templates/configs, running CSB usage/analysis/refine/dev commands remotely, handling reconnects and cleanup, coordinating multiple remote machines, and copying results/reports/configs/monitor artifacts back into remote-specific result directories on the host."
---

# CSB Remote

Use this skill whenever a CSB benchmark, refinement, analysis rerun, monitor capture, source checkout, build, or validation is performed on an SSH-accessible remote machine instead of the controller host running Codex.

## Roles

- **Controller host**: the machine running the AI agent. It owns the Codex skills, local instructions, final copied reports, and cross-remote organization.
- **Remote benchmark host**: the machine that executes CSB commands, benchmarks, monitors, package installs, source checkouts, kernel-source correlation, builds, and cleanup.
- Treat the remote as the source of truth for benchmark outputs, system/kernel facts, monitor availability, and tested source trees. The controller can generate or edit skill-guided scripts/configs, but every runtime check and benchmark command must be executed remotely.

## Skill Composition

Use this skill with the relevant CSB skill:

- `csb`: choose/adapt configs and run campaigns remotely.
- `csb-analysis`: analyze remote result artifacts and perform source/perf inspection against the remote's tested kernel/source tree.
- `csb-refine`: perform every sweep, cleanup, monitor adaptation, diagnostic run, report generation, and patch/object-build test remotely.
- `csb-dev`: reproduce framework bugs, run tests, and validate monitor/runner changes remotely when the behavior depends on remote-only permissions, hardware, kernel, containers, perf, bpftrace, or topology.

When instructions in another CSB skill say "host", "machine", "testing machine", "local command", or "prepare the environment", interpret that as the remote benchmark host for remote work. Keep only final aggregation, copied artifacts, and skill files on the controller unless explicitly asked to edit the remote checkout.

## Remote Inventory

For each remote, record a short inventory before running CSB:

```bash
ssh <remote> 'hostname; pwd; uname -a; cat /etc/os-release 2>/dev/null || true; nproc; lscpu | sed -n "1,80p"'
ssh <remote> 'command -v git python3 sudo perf bpftrace docker runc youki mpstat iostat || true'
ssh <remote> 'test -d /path/to/csb && git -C /path/to/csb status --short || true'
```

Keep this mapping in notes or reports:

- remote name and SSH target;
- remote CSB checkout path;
- remote result group/root;
- remote kernel/source tree path, usually `deps/linux`;
- runtime/container tools and monitor permissions;
- any node-specific cleanup/runtime quirks.

Multiple remotes may be used simultaneously. Prefix tmux sessions, result groups, temp configs, and copied directories with the remote name so artifacts do not collide.

## Remote Setup

The remote must have a complete CSB setup with all dependencies needed by the selected CSB skills. Execute the checks and setup on the remote:

```bash
ssh <remote> 'cd /path/to/csb && scripts/prepare.sh'
ssh <remote> 'cd /path/to/csb && cmake -S. -Bbuild && cmake --build build -j"$(nproc)"'
ssh <remote> 'cd /path/to/csb && python3 -m json.tool config/<file>.json >/dev/null'
```

Install missing software on the remote, not the controller, when needed for the requested benchmark or monitors. Typical packages/tools include Python build dependencies, CMake, Docker or the selected OCI runtime, sysstat (`mpstat`/`iostat`), `perf`, `bpftrace`, benchmark-specific `*-dev` packages, and kernel build/source dependencies.

For perf, tracefs, bpftrace, Arm SPE, containers, cgroups, NICs, and kernel-source setup, run the permission and availability commands from `csb`, `csb-analysis`, and `csb-refine` on the remote. Do not infer remote capability from the controller.

## Source Trees

Kernel source used for source correlation and object-build tests belongs on the remote unless the user explicitly asks for host-only analysis. Use one remote `deps/linux` tree:

- add or update a Torvalds remote for upstream comparison;
- add or update the tested distro/vendor/kernel remote;
- check out the branch/tag/commit closest to the running remote kernel;
- record remotes, checked-out commit, dirty state, and comparison ref in reports.

If host skills provide bpftrace templates, helper scripts, or report generators that are not present remotely, copy those files to a temporary remote path or into the remote CSB checkout before running. Treat controller copies as templates; executed scripts and generated programs should live in the remote run artifacts and be copied back afterward.

## Running Remotely

Run CSB through SSH from the remote CSB checkout:

```bash
ssh <remote> 'cd /path/to/csb && CSB_RESULTS_GROUP=<remote>_<group> scripts/run-single.sh config/<file>.json'
```

For long runs, use `tmux` or `systemd-run` on the remote and reconnect until completion:

```bash
ssh <remote> 'cd /path/to/csb && tmux new-session -d -s csb_<remote>_<name> "CSB_RESULTS_GROUP=<group> scripts/run-single.sh config/<file>.json 2>&1 | tee results/<group>.log"'
ssh <remote> 'tmux capture-pane -pt csb_<remote>_<name> -S -200'
```

If the SSH connection drops, reconnect and inspect the remote session/processes. Do not restart a sweep until you know whether the prior sweep is still running, completed, or failed and cleanup is needed.

## Cleanup Between Sweeps

Before every new remote CSB sweep, perform the cleanup required by `csb-refine` on that remote. Clean only artifacts belonging to the prior CSB sweep:

- stale benchmark/application processes;
- stale Docker/runc/youki/runtime state with the benchmark prefix;
- stale monitor processes such as `perf`, `perf lock`, `bpftrace`, `mpstat`, `iostat`;
- CSB start barriers such as `build/bench/start`;
- temporary monitor files, oversized partial perf data, and scratch dirs not meant to be kept.

Re-check after cleanup with process/runtime-specific commands. Record the cleanup summary in the remote run report.

## Copy-Back Layout

At the end of each remote task, copy all final results, reports, configs, generated bpftrace programs, helper scripts, and patch artifacts back to the controller under a remote-specific directory. Prefer this layout:

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

Use `rsync -a --info=progress2` or `scp -r` from the controller. For large `perf.data`, flamegraphs, or traces, copy only the artifacts needed for analysis unless the user asks for full raw data. Preserve remote filenames and run basenames so CSB result sibling relationships remain recognizable.

For multiple remotes, keep one subtree per remote and add a top-level cross-remote index/report only after all per-remote artifacts are copied.

## Reporting

Remote reports must state:

- which commands ran remotely and which ran on the controller;
- remote hostname, kernel, CPU/topology, cgroup mode, runtime, monitor availability, and source tree commits;
- cleanup performed before each sweep;
- copied-back artifact paths on the controller;
- any remote-only installs, permission changes, sudo limitations, reconnects, or failed monitor probes;
- whether raw data stayed remote due to size, and how to retrieve it if needed.

When the user asks for "all reports/results/configs copied back", verify the controller copy has the expected Markdown/HTML/CSV/JSON/result directories before finishing.
