# cgroup v2 stress tests

These external benchmarks exercise cgroup v2 kernel paths that become hot when many
CSB execution units run at once. They are intended to run with CSB's `container`
execution environment so the benchmark count controls the number of concurrent
privileged containers.

Each script emits CSB-compatible `key=value;` metrics directly.

## Tests

- `cgv2_lifecycle.sh`: creates/removes many child cgroups and repeatedly writes
  `cgroup.procs`, approximating the cgroup management path used by container
  creation and teardown.
- `cgv2_limits_pids.sh`: repeatedly writes `pids.max`, attaches tasks, and drives
  fork failures through the pids controller.
- `cgv2_limits_memory.sh`: writes `memory.high`/`memory.max` and allocates memory
  inside per-worker cgroups to trigger charge, reclaim, and memory event paths.
- `cgv2_rstat_pressure.sh`: builds many cgroup leaves, runs CPU-burning tasks in
  them, and concurrently reads `cgroup.stat`, `cpu.stat`, and `memory.stat` to
  force cgroup rstat flush work.

Run one with:

```bash
scripts/run-single.sh config/cgroupv2-stress/cgv2_lifecycle.json
```

The benchmark requires a writable cgroup v2 mount in the execution environment.
