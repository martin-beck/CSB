# Monitor And Linux Source Map

Use this reference after the first-pass report identifies candidate bottlenecks.

## CSB Run Layout

A complete run is a basename with:

- `results/<base>/` for per-parameter monitor artifacts.
- `results/<base>.json` for copied run configuration.
- `results/<base>.html` for plots.
- `results/<base>.csv` for benchkit result rows.

Per-parameter monitor files usually sit below:

`nb_threads-*/noise-*/initial_size-*/container_cnt-*/execution_type-*/run-*/`

Preserve these path dimensions in notes. A lock or perf sample at `container_cnt-30` cannot be treated as evidence for `container_cnt-1`.

## CSV Signals

Common result columns:

- `container_cnt`, `nb_threads`, `execution_type`, `rep`, `benchmark_name`, `hostname`, `architecture`
- `throughput_min`, `throughput_max`
- `univ_avg`, `univ_min`, `univ_max`, `univ_succ_percent`
- benchmark-specific columns such as `<op>_avg`, `<op>_succ_percent`, `<op>_count`
- mpstat-derived columns such as `usr_c0`, `sys_c0`, `iowait_c0`, `idle_c0`, `intr_c0`, `RCU_c0`, `SCHED_c0`
- `kernel`, `Allowed CPUs`, `cgroup`

Prefer `throughput_min` for conservative scaling. If only benchmark-specific throughput exists, document the chosen column.

## Perf

Useful commands when `perf.data` is present and host permissions allow it:

```bash
perf report --stdio -i <perf.data> --sort symbol,dso --percent-limit 0.5
perf script -i <perf.data> | head
perf stat -x ';' -I 1000 ...
```

Source correlation patterns:

- scheduler: `kernel/sched/`, `kernel/locking/`, `kernel/rcu/`
- filesystem/page cache: `fs/`, `mm/filemap.c`, `mm/page-writeback.c`
- block I/O: `block/`, `drivers/nvme/`, `drivers/md/`, `fs/iomap/`
- network/container setup: `net/core/`, `net/netlink/`, `net/ipv4/`, `net/sched/`
- cgroup: `kernel/cgroup/`, `kernel/sched/core.c`, `mm/memcontrol.c`
- futex and user synchronization: `kernel/futex/`

Use `rg '^<symbol>\\b|\\b<symbol>\\s*\\(' deps/linux` first. If the symbol includes `.isra`, `.constprop`, or an offset, strip compiler suffixes and `+0x...`.

## Lock Contention

`lock-contention.csv` fields are usually:

`contended; total wait; max wait; avg wait; type; caller`

Interpretation:

- Sort by `total wait` to find throughput bottlenecks.
- Sort by `avg wait` or `max wait` to find tail latency risks.
- Map `caller` to source, then walk up the subsystem. A caller often identifies where the lock was acquired, not necessarily the complete logical bottleneck.
- For `rtnl`, `netlink`, `ioctl`, and container-heavy results, inspect `net/core/rtnetlink.c`, `net/netlink/`, device setup paths, and namespace/cgroup interactions.
- For ext4 or writeback callers, inspect `fs/ext4/`, `fs/buffer.c`, `mm/page-writeback.c`, and block-layer queues.

## mpstat

Use `mpstat.json` to test whether degradation is CPU saturation or kernel pressure:

- rising `sys` with falling throughput suggests kernel overhead or lock contention;
- rising `iowait` suggests storage or memory reclaim stalls;
- rising `soft`/`NET_RX`/`NET_TX` suggests network/softirq pressure;
- rising `RCU` or `SCHED` interrupts with low user work suggests scheduler/RCU overhead;
- high idle with low throughput suggests external serialization, sleep/wakeup, I/O waits, or monitor/config problems.

## iostat

Correlate throughput cliffs with:

- `%util` near saturation;
- high `await` or `aqu-sz`;
- large writeback spikes;
- asymmetric device pressure across runs.

Then inspect block, filesystem, and storage-driver code rather than scheduler code first.

## Arm SPE

For SPE-derived evidence, focus on source-attributed memory latency:

- load/store stalls in scheduler or locking code suggest shared data bouncing;
- page table, mmap, or allocator stalls point toward `mm/`;
- device or DMA path stalls point toward driver/block/network subsystems.

Always report SPE tooling/version assumptions because decode output varies by platform.

## bpftrace

Read the bpftrace program and output together. Useful source pivots:

- syscall counts/latency: syscall implementation and VFS/network wrappers;
- scheduler tracepoints: `kernel/sched/`;
- block tracepoints: `block/`, filesystem writeback paths;
- kprobes on locks: `kernel/locking/` and caller subsystem;
- cgroup tracepoints: `kernel/cgroup/` and controller-specific files.

## Kernel Patch Direction

Good CSB-derived patch proposals usually target one of:

- reducing global lock hold time or splitting a heavily contended lock;
- batching per-container/process operations;
- replacing global counters/lists with per-CPU/per-node state;
- deferring expensive work outside hot paths;
- improving NUMA locality or avoiding cross-node bouncing;
- reducing redundant cgroup, namespace, netlink, or filesystem work under high process/container counts.

Do not propose broad rewrites without showing why a smaller measurable change is insufficient.
