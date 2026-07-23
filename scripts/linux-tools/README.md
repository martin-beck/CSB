# Linux tool trace corpus

This harness sets up and traces safe, short examples for 100 commonly used
Linux command-line tools. The order in `tools.tsv` is a practical corpus chosen
for breadth and everyday prevalence, not a telemetry-derived universal ranking.

## Usage

Run these commands from the CSB repository root. List the ranked corpus and its
operation recipes without installing anything:

```bash
scripts/linux-tools/run.sh --list
scripts/linux-tools/sweep.sh --plan
```

Set up one tool, run its example without tracing, or capture its trace:

```bash
scripts/linux-tools/setup.sh grep
scripts/linux-tools/run.sh --no-trace grep micro
scripts/linux-tools/run.sh --trace grep micro
```

Each tool has two workload tags:

- `micro` preserves the original one-shot smoke example.
- `small` prepares a realistic temporary dataset or state and exercises several
  normal operations and option paths for approximately ten seconds. It is a
  distinct workload, not a loop around the micro recipe or a repeated help
  command, and it performs useful work throughout the interval.

The small-workload duration defaults to 10 seconds and can be changed for one
tool or a complete sweep:

```bash
scripts/linux-tools/run.sh --trace grep small
scripts/linux-tools/run.sh --trace --duration 30 grep small
scripts/linux-tools/sweep.sh --trace --run small --duration 30
```

`run.sh` sets up a missing tool automatically, so calling `setup.sh` first is
optional. To prepare or trace the complete corpus:

```bash
scripts/linux-tools/setup.sh --all
scripts/linux-tools/sweep.sh --trace --run all
```

Every successful `setup.sh` installation is immediately launched with a safe,
tool-specific version or help probe. This detects missing libraries, invalid
executables, wrong-architecture binaries, and prefix-path escapes before the
tool is used. Validation logs are retained under `PREFIX/validation/`. It can
also be rerun independently without reinstalling anything:

```bash
scripts/linux-tools/validate.sh grep
scripts/linux-tools/validate.sh --all
```

Use `setup.sh --list` or `run.sh --list` to see all tools and recipes. `--plan`
does not install or run anything; `--no-trace` runs a workload without strace.
Traces go to `traces/<architecture>/<tool>/<workload>.strace` with the standard
CSB `.meta` sidecar, and existing traces are never overwritten. A sweep runs
both workload tags by default; use `--run micro` or `--run small` to select one.

Use separate paths for different machines or runs:

```bash
PREFIX=/tmp/my-tools WORK_DIR=/tmp/my-work TRACE_DIR=/tmp/my-traces \
  scripts/linux-tools/run.sh --trace jq
```

The same variables apply to `setup.sh` and `sweep.sh`. Reusing `PREFIX` avoids
downloading and extracting tools again. Use a new `TRACE_DIR` for another trace
run because existing traces are deliberately preserved.

## Disk-space requirements

Exact usage depends on the distribution, architecture, package versions, and
dependency layout. A complete setup typically requires approximately:

- **4–6 GiB** for extracted tools and their dependency closure.
- **1–2 GiB** for retained package archives.
- **0.2–1 GiB** for operation work directories.
- **1–4 GiB** for one complete set of 100 traces. Compiler and language-tool
  traces are usually the largest and can push this higher.

Allow at least **10 GiB** of free space. **15 GiB** is recommended for a full
setup and trace sweep, while **20 GiB** is more comfortable when retaining
multiple trace sets. Package archives below `PREFIX/packages/` are not needed
to run already extracted tools and may be removed later if their cached
downloads are no longer required.

`PREFIX` and `WORK_DIR` default below `${TMPDIR:-/tmp}`. Setup always downloads
and extracts a native package into the prefix; it never symlinks or selects the
host's copy of a corpus tool. apt/dpkg, dnf/RPM, zypper/RPM, apk, and pacman are
supported. Package extraction is best-effort because distributions sometimes
split runtime libraries differently; failures name the tool and package.

The host shell, package manager, downloader, and archive utilities are the
bootstrap boundary used to populate and drive the prefix. The selected tool
(and `strace` in trace mode) are resolved exclusively below `PREFIX`.

All mutations are confined to a freshly recreated per-tool directory. Host
inspection is read-only, network examples use loopback, and privileged tools
only query state. Micro runs have a seven-second hard limit; small runs have a
duration-based limit with a short cleanup margin. The harness never uses sudo.
