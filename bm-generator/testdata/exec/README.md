# Exec trace fixtures

`exec_fixture.c` records every supported libc exec entry point in a bounded
fork/wait lifecycle. The child either replaces itself or exits immediately;
the parent always waits for that exact child.

Refresh and validate the checked-in traces with:

```bash
bm-generator/testdata/exec/test.sh
```

The libc calls `execl`, `execle`, `execlp`, `execv`, `execvp`, and `execvpe`
all enter the kernel through `execve`, so their logs intentionally share that
kernel mapping. `fexecve` is libc-dependent and may use `execveat` or an
`execve` path through `/proc/self/fd`. Separate direct `execveat` fixtures use
a path and `AT_EMPTY_PATH`. `strace-all.log` contains every mapping in one application.

The logs include loader activity from the fixture and `/bin/true`; generator
tests should select the exec calls rather than assuming the logs contain only
one syscall.
