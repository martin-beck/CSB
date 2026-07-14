# Task-lifecycle generator fixtures

These short programs provide real strace inputs for the task-creation mappings:

| Fixture | Expected trace | Lifecycle |
|---|---|---|
| `pthread_create.c` | pthread-style `clone` or `clone3` | create and join a thread |
| `fork.c` | libc `fork` (often printed as `clone`) | child `_exit`, exact-PID wait |
| `vfork.c` | libc `vfork` | child `_exit`, exact-PID wait |
| `clone.c` | process-style libc `clone` | child return, exact-PID wait |
| `clone3.c` | process-style raw `clone3` | child `_exit`, exact-PID wait |
| `combined.c` | all of the above | each lifecycle runs in sequence |

Run `./record-traces.sh` to compile the fixtures in `/tmp` and refresh `traces/`.
The focused syscall filter keeps the checked-in logs small while preserving the
format consumed by `02_parse.sh`. A host seccomp profile may make `clone3` return
`ENOSYS`; this is a valid parser/classifier input and the fixture accepts it.

Run `./test-fixtures.sh` to refresh the logs and execute 16 instances of every
fixture concurrently under a timeout. This checks that each fixture completes
and reaps or joins the task it creates.

After building the syzkaller tools, each trace can be passed independently to:

```sh
cd bm-generator
./02_parse.sh tests/task-lifecycle/traces/pthread_create.strace
./03_extract.sh
./04_prepare.sh
```

Generator output directories must be empty before starting another trace, as
documented in `doc/bm-generator.md`.
