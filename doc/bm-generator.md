# CSB Generator

CSB generator found in bm-generator is a tool that extends [syzkaller][] and uses [tmplr][] to auto-generate benchmarks and JSON configuration files
compatible with the CSB framework [bm-runner][].

The generator takes a [strace][] log file as input.

## Disclaimer
This tool is currently experimental and still in the prototype phase.

At the moment, users are expected to run benchmark generation scripts on the target machine, where the benchmarks
will be run and analyzed.

## Requirements

### Install Go

[syzkaller][] requires Go 1.25.x or newer.

The `golang-go` package shipped by Ubuntu 22.04 is too old for this workflow.

You can install [Go][] as follows:
```bash
cd bm-generator/helper/
./install_go.sh
```

Make sure to add the golang binary directory to your PATH environment variable and re-login to your terminal session.
Put the following line into `$HOME/.bashrc`
```bash
export PATH=$PATH:/usr/local/go/bin
```

If installation fails, use the following instructions:

1. Verify if golang is installed with the correct version
```bash
go version
# result should be "go version go1.25.x ..."
```
2. If the version is incorrect *and* go is installed, then uninstall it with
  ```bash
  sudo apt remove golang-go
  ```
  - Check that has worked with
  ```bash
  ls /usr/local/go
  ```
  - If the directory is not empty, then uninstall it with:
  ```bash
  rm -rf /usr/local/go
  ```
3. Download Go from the official website:
```bash
wget https://go.dev/dl/go1.25.5.linux-amd64.tar.gz
```
  - Note: make sure that the file downloaded match your architecture (i.e., amd64 for x86-64 and arm64 for Arm).
4. Decompress file and place it in executables directory
```bash
tar -C /usr/local -xzf go1.25.5.linux-amd64.tar.gz
```
5. Add directory into PATH environment variable by adding the following line into `$HOME/.bashrc`
```bash
export PATH=$PATH:/usr/local/go/bin
```
  - Note: this change is only applied by closing and then reopening the terminal
6. Check that the correct golang was installed with
```bash
go version
# result should be "go version go1.25.x ..."
```

For more details, you can check the go installation website:
https://go.dev/doc/install


## Generating Benchmarks

The pipeline for generating benchmarks is implemented in
the following scripts within `bm-generator/`:

|Script|Description|
|---|---|
|`00_init.sh`| Checks that Go 1.25 or newer is available and offers to install it when it is missing. |
|`01_build.sh`| Configures the CSB build when necessary and builds the required syzkaller tools. |
|`02_parse.sh`| Translates one strace log into [syzlang][] programs stored directly in `deserialized/*.prog`, then prints translation coverage. With a report-capable `syz-trace2syz`, it also stores `deserialized/translation_report.txt`. |
|`03_extract.sh`| Extracts dependency-preserving programs from each `deserialized/*.prog` input. Results are stored below a numbered directory per input, such as `extracted/0/*.prog`. |
|`04_prepare.sh`| Recursively converts `extracted/**/*.prog` into CSB headers under `../bench/targets/<group>/syz/`. |
|`05_generate.sh`| Uses [tmplr][] to generate bm-runner-compatible wrapper headers in `../bench/targets/<group>/` and flamegraph JSON configurations in `../config/<group>/`. |
|`06_select.sh`| Runs the generated flamegraph configurations briefly, compares their flamegraphs, and writes the selected benchmark set and merged output under `../bench-select/`. |
|`99_clean.sh`| Shows generated headers and configurations that can be removed, then asks for confirmation. `-f` skips confirmation and `-a` also includes intermediate and build directories. |

Of the numbered generation stages, only `02_parse.sh` requires a positional
argument: the path to an strace log generated as described below.
```bash
./02_parse.sh </path/to/strace.log>
```

### Collect strace

Use the following [strace][] command to collect `strace.log`.

_Note: replace `<app-binary>` with the name of your binary/application including all necessary arguments._

Install `strace` with your distribution's package manager before collecting a
trace.

```bash
../scripts/plugins/collect_strace.sh strace.log <app-binary> [arguments...]
```

Alternatively:

```bash
strace -o strace.log -a 1 -s 65500 -v -xx -f -Xraw --raw=wait4 <app-binary>
```

The scripts should be run in the same order they are enumerated:

```bash
cd bm-generator/
./00_init.sh
./01_build.sh
./02_parse.sh strace.log
./03_extract.sh
./04_prepare.sh
./05_generate.sh
./06_select.sh
```

`02_parse.sh` refuses to write into a non-empty deserialization directory, and
`06_select.sh` refuses to overwrite an existing result group. `04_prepare.sh`
warns when the target directory already exists because mixing generated sets can
produce misleading results. Use `./99_clean.sh` to inspect the generated paths
before removing them; add `-a` to include intermediate and build directories.

The default group is `gen-ws`. To generate another group, set
`CSB_RESULTS_GROUP` before `01_build.sh` configures CMake and keep it set for
stages 04 through 06. The extraction stage can also be tuned with `MINCALLS`
(default 10) and `JOBS` (default number of processors).

## CSB syzkaller fork

The CSB syzkaller fork extends upstream syzkaller primarily in these areas:

- `tools/syz-trace2syz/`: strace parsing and `.prog` serialization. Notable
  flags include `-deserialize`, `-nocorpus`, `-topCalls`, `-splitThreads`, and
  `-argLength`. Deserialization also writes `translation_report.txt` with
  syscall coverage and exact source-to-helper mappings.
- `prog/`: serialization/deserialization and CSB-specific annotations such as
  strace TIDs, return values, clone/resource annotations, and dependency
  minimization helpers.
- `tools/syz-extraction/`: dependency minimization, poll filtering,
  deterministic TID iteration, and minimum call count filtering.
- `tools/syz-prog2c/` and `pkg/csource/`: C/CSB header generation, path, socket
  and file sanitization, file descriptor lifecycle handling, shared buffers,
  metadata, and CSB config output.
- `executor/` and `sys/linux/sys.txt*`: runtime helpers and syscall
  descriptions when needed.

Build the syzkaller tools from the nested repository:

```bash
cd deps/syzkaller
make trace2syz prog2c extraction
```

Focused tests for syzkaller-side CSB changes:

```bash
cd deps/syzkaller
go test ./tools/syz-trace2syz/parser ./tools/syz-trace2syz/proggen
go test ./prog ./pkg/csource
go test ./tools/syz-extraction ./tools/syz-prog2c ./tools/syz-trace2syz
```

## Deduplicating the set of autogenerated microbenchmarks:

The benchmarks generated by bm-generator may contain redundancy: for example, system call sequences that differ only in a file name in the same directory will be considered to be different, even though their effect on the system is the same.

To filter out such benchmarks, we introduce a pipeline based on flamegraph difference calculation:
- For each benchmark, the flamegraph is recorded and post-processed (see details below).
- Each of the collapsed stacks of the flamegraph is passed to `diffolded.pl` to calculate the difference of flamegraphs, and the maximum detected difference for a single stack (in either diff direction) is reported.
- Benchmarks which differ from each other by less than a certain threshold are considered to be the same, and only one of them is kept.

Before passing the stacks to the `difffolded.pl` the flamegraph is postprocessed: in particular, the userspace stacks are dropped from the flamegraph, and only kernel stacks are kept.
Furthermore, the name of the benchmark application is replaced with a generic one. This works around a `difffolded.pl` limitation that permits calculating the difference only for applications with the same name.
This directly allows comparing the postprocessed flamegraphs of the autogenerated microbenchmarks with each other as well as with the postprocessed flamegraph of the original application.

To run the benchmarks selection pipeline after generation of the microbenchmarks, you can run:
```bash
./06_select.sh
```
Alternatively, you can use the manual workflow outlined below.

### Manual workflow

To perform the deduplication, CSB provides a set of scripts in the `CSB/scripts/fg-diff` directory, driven by `./CSB/scripts/fg-diff/select-benchmarks.sh` script.
The operation workflow looks like the following:
```
$ cd CSB # this is important; the script will not work from a different directory
$ ./scripts/fg-diff/select-benchmarks.sh ./config/min_mysql_*.json
```
The last command takes as arguments the list of JSON config files of the microbenchmarks to execute for inclusion into the comparison.
In case no config files are provided, no new benchmarks are executed and only the results already present in the `results` directory are taken into account.

The output of the script is a list of benchmark names that are distinct from each other, according to the flamegraph difference criterion.

## Translation coverage

Translation support depends on the trace contents, target architecture, and
syzkaller revision, so a static excluded-syscall list quickly becomes stale.
After parsing, `02_parse.sh` reports the input syscall names and calls, direct
syzlang translations, calls represented by CSB helper functions, and calls that
were not translated. Exact source-syscall-to-helper mappings are included when
helpers are used. The machine-readable source is
`deserialized/translation_report.txt`.

When the installed `syz-trace2syz` does not produce that report, the helper
falls back to comparing direct syscall names in the strace and generated
programs. This compatibility mode cannot account for calls implemented by CSB
helper functions, so use the report-capable syzkaller revision for complete
coverage statistics.


## Generating JSON files

Users can generate JSON files for any group of generated benchmark headers.
The generator reads input headers from:
`bench/targets/<group>/syz/*.h` and writes the generated JSON files to `config/<group>/`

By default, `<group>` is `gen-ws`. To generate JSON files for another group,
set the environment variable `CSB_RESULTS_GROUP` before running the CMake build target.

For example, to generate JSON files for headers in `bench/targets/my-group/syz/`:

```bash
cd csb
export CSB_RESULTS_GROUP=my-group
cmake -S. -B build -DCSB_BM_GENERATOR=ON
cmake --build build --target bm_single.json.in
```
Note that `bm_single.json.in` is a template that exists under `bm-generator/templates/`.
Users can also create their own templates and generate for them, provided that
the template name matches `*single*.json.in`

[strace]: https://github.com/strace/strace
[tmplr]: https://github.com/open-s4c/tmplr
[syzkaller]: https://github.com/open-s4c/syzkaller/tree/s4c/csb-dev
[bm-runner]: bm-runner.md
[Go]: https://go.dev/doc/install
[syzlang]: https://github.com/google/syzkaller/blob/master/docs/syscall_descriptions_syntax.md
