#!/usr/bin/env python3
"""Generate CSB result analysis reports from completed result artifacts."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import os
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from statistics import mean


RUN_RE = re.compile(r"^(?P<prefix>.+?)_(?P<date>\d{8})_(?P<time>\d{6})_(?P<usec>\d{6})$")
COMPILER_SUFFIX_RE = re.compile(r"(\.constprop\.\d+|\.isra\.\d+|\.part\.\d+)$")
SOURCE_LOOKUP_CACHE: dict[tuple[str, str], list[tuple[str, int, str]]] = {}

SYSCALL_SOURCE_MAP = {
    "faccessat2": [("fs/open.c", "do_faccessat"), ("fs/namei.c", "user_path_at_empty")],
    "fallocate": [("fs/open.c", "ksys_fallocate"), ("fs/ioctl.c", "ioctl_preallocate")],
    "fcntl": [("fs/fcntl.c", "do_fcntl"), ("fs/locks.c", "fcntl_setlk")],
    "fsync": [("fs/sync.c", "ksys_fsync"), ("fs/fs-writeback.c", "wb_workfn")],
    "getdents64": [("fs/readdir.c", "iterate_dir"), ("fs/readdir.c", "filldir64")],
    "lseek": [("fs/read_write.c", "ksys_lseek"), ("fs/read_write.c", "vfs_llseek")],
    "newfstatat": [("fs/stat.c", "do_statx"), ("fs/stat.c", "vfs_statx")],
    "openat": [("fs/open.c", "do_sys_openat2"), ("fs/namei.c", "path_openat")],
    "pread64": [("fs/read_write.c", "ksys_pread64"), ("mm/filemap.c", "filemap_read")],
    "pwrite64": [("fs/read_write.c", "ksys_pwrite64"), ("mm/filemap.c", "generic_perform_write")],
    "read": [("fs/read_write.c", "ksys_read"), ("mm/filemap.c", "filemap_read")],
    "readlinkat": [("fs/stat.c", "do_readlinkat"), ("fs/namei.c", "vfs_readlink")],
    "recvfrom": [("net/socket.c", "__sys_recvfrom"), ("net/core/datagram.c", "skb_copy_datagram_iter")],
    "sendto": [("net/socket.c", "__sys_sendto"), ("net/core/sock.c", "sock_sendmsg")],
    "setsockopt": [("net/socket.c", "__sys_setsockopt"), ("net/core/sock.c", "sock_setsockopt")],
    "write": [("fs/read_write.c", "ksys_write"), ("mm/filemap.c", "generic_perform_write")],
}

SOURCE_DIRS = ("arch", "block", "drivers", "fs", "include", "kernel", "mm", "net")
SOURCE_SUBSYSTEM_HINTS = (
    ("fs/ext4/", "ext4 filesystem"),
    ("fs/xfs/", "xfs filesystem"),
    ("fs/btrfs/", "btrfs filesystem"),
    ("fs/", "VFS/filesystem"),
    ("block/", "block layer"),
    ("mm/", "memory management"),
    ("net/", "network stack"),
    ("kernel/sched/", "scheduler"),
    ("kernel/locking/", "locking"),
    ("kernel/rcu/", "RCU"),
    ("kernel/cgroup/", "cgroup"),
    ("drivers/nvme/", "NVMe driver"),
    ("drivers/scsi/", "SCSI driver"),
    ("drivers/", "driver"),
    ("arch/arm64/", "arm64 architecture"),
)

PATTERN_TERMS = {
    "spin": ("native_queued_spin_lock_slowpath", "queued_spin_lock", "qspinlock", "cmpxchg"),
    "mutex": ("osq_lock", "__mutex_lock", "mutex_lock", "mutex_spin_on_owner"),
    "wakeup": ("futex_wake", "try_to_wake_up", "wake_up_q", "ttwu_queue", "sched_yield"),
    "scheduler": ("__schedule", "schedule", "finish_task_switch", "io_schedule"),
    "flush": (
        "vfs_fsync",
        "vfs_fsync_range",
        "ext4_sync_file",
        "blkdev_issue_flush",
        "submit_bio_wait",
        "jbd2",
        "blk_mq",
        "filemap_fdatawrite",
    ),
    "ext4": ("ext4_fallocate", "vfs_fallocate", "ext4_file_write_iter", "ext4_file_read_iter"),
    "path": (
        "do_sys_openat2",
        "path_openat",
        "link_path_walk",
        "filename_lookup",
        "vfs_faccessat",
        "vfs_statx",
        "do_faccessat",
    ),
    "rw": ("vfs_read", "vfs_write", "new_sync_read", "new_sync_write", "iov_iter", "copy_page"),
    "net": ("tcp_recvmsg", "tcp_sendmsg", "sock_recvmsg", "sock_sendmsg", "skb", "inet_recvmsg"),
    "accounting": ("percpu_counter", "__percpu", "this_cpu", "atomic64_add", "atomic_long_add", "refcount"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_dir", nargs="?", default="results")
    parser.add_argument(
        "--out",
        default="-",
        help=(
            "Markdown output path, '-' for stdout, or a path containing "
            "{base}, {run_prefix}, {benchmark}, {system}, or {timestamp} placeholders"
        ),
    )
    parser.add_argument("--linux", default="deps/linux", help="Linux source directory to reference")
    parser.add_argument("--no-html", action="store_true", help="Do not write adjacent HTML for Markdown outputs")
    parser.add_argument(
        "--summary-out",
        help=(
            "Write a cross-run summary Markdown file after per-run reports. "
            "Use with placeholder --out to keep per-run analysis independent."
        ),
    )
    parser.add_argument("--top-locks", type=int, default=8)
    parser.add_argument("--top-monitor-files", type=int, default=80)
    return parser.parse_args()


def load_md_renderer():
    renderer_path = Path(__file__).with_name("md_to_html.py")
    spec = importlib.util.spec_from_file_location("csb_analysis_md_to_html", renderer_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load Markdown renderer from {renderer_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_markdown_and_html(path: Path, text: str, emit_html: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    if emit_html:
        load_md_renderer().render_file(path)


def read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    lines = [line for line in path.read_text(errors="replace").splitlines() if line and not line.startswith("#")]
    if not lines:
        return [], []
    dialect = csv.Sniffer().sniff("\n".join(lines[:5]), delimiters=";,")
    reader = csv.DictReader(lines, dialect=dialect)
    return list(reader.fieldnames or []), list(reader)


def number(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip().strip('"')
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    try:
        v = float(text)
    except ValueError:
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


def grouped(rows: list[dict[str, str]], keys: list[str]):
    groups: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[tuple(row.get(k, "") for k in keys)].append(row)
    return groups


def avg(rows: list[dict[str, str]], col: str) -> float | None:
    vals = [number(r.get(col)) for r in rows]
    vals = [v for v in vals if v is not None]
    return mean(vals) if vals else None


def fmt(v: float | None, digits: int = 2) -> str:
    return "n/a" if v is None else f"{v:.{digits}f}"


def md_link(label: str, href: str) -> str:
    label = label.replace("[", "\\[").replace("]", "\\]")
    href = href.replace(" ", "%20")
    return f"[{label}]({href})"


def local_file_link(label: str, target: Path, from_dir: Path, line: int | None = None) -> str:
    rel = Path(os.path.relpath(target, from_dir)).as_posix()
    if line is not None:
        rel = f"{rel}#L{line}"
    return md_link(label, rel)


def run_parts(base: str) -> tuple[str, str, str]:
    m = RUN_RE.match(base)
    if not m:
        return "unknown", base, "unknown"
    prefix = m.group("prefix")
    timestamp = f"{m.group('date')} {m.group('time')}.{m.group('usec')}"
    parts = prefix.split("_")
    system = parts[1] if parts and parts[0] == "benchmark" and len(parts) > 1 else parts[0]
    benchmark = "_".join(parts[2:] if parts and parts[0] == "benchmark" and len(parts) > 2 else parts[1:])
    return system, benchmark or prefix, timestamp


def run_prefix(base: str) -> str:
    m = RUN_RE.match(base)
    if not m:
        return base
    parts = m.group("prefix").split("_")
    if parts and parts[0] == "benchmark" and len(parts) > 1:
        return "_".join(parts[:2])
    return parts[0] if parts else base


def safe_name(value: str) -> str:
    value = value.strip().replace(" ", "_").replace(".", "_")
    value = re.sub(r"[^A-Za-z0-9_-]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("._")
    return value or "unknown"


def discover_runs(results_dir: Path):
    bases = set()
    for p in results_dir.iterdir() if results_dir.exists() else []:
        if p.is_dir():
            bases.add(p.name)
        elif p.suffix in {".json", ".csv"}:
            bases.add(p.stem)
    for base in sorted(bases):
        yield {
            "base": base,
            "dir": results_dir / base,
            "json": results_dir / f"{base}.json",
            "html": results_dir / f"{base}.html",
            "csv": results_dir / f"{base}.csv",
        }


def collect_runs(results_dir: Path) -> tuple[list[dict[str, Path | str]], list[tuple[dict[str, Path | str], list[str]]]]:
    complete = []
    incomplete = []
    for run in discover_runs(results_dir):
        missing = [k for k in ("dir", "json", "html", "csv") if not run[k].exists()]
        if missing:
            incomplete.append((run, missing))
        else:
            complete.append(run)
    return complete, incomplete


def summarize_config(path: Path) -> tuple[str, str]:
    if not path.exists():
        return "n/a", "n/a"
    try:
        data = json.loads(path.read_text(errors="replace"))
    except Exception as exc:  # noqa: BLE001
        return f"unreadable: {exc}", "n/a"
    monitors = data.get("benchmark_config", {}).get("monitors", {})
    apps = data.get("applications", [])
    app_names = [str(a.get("name") or a.get("app") or a.get("path") or a) for a in apps if isinstance(a, dict)]
    return ", ".join(monitors.keys()) or "none", ", ".join(app_names) or "n/a"


def monitor_inventory(run_dir: Path) -> dict[str, list[Path]]:
    patterns = {
        "perf": ["perf.log", "perf.err", "perf.data", "perf-lock.log", "perf-lock.err"],
        "flamegraph": ["flamegraph.stacks", "flamegraph.errors", "flamegraph.svg"],
        "lock": ["lock-contention.csv", "lock-contention.errors", "perf-lock.log"],
        "c2c": ["*c2c*"],
        "mpstat": ["mpstat.json", "mpstat.err"],
        "iostat": ["iostat*.json", "iostat*.log", "iostat*.txt", "iostat*.err"],
        "spe": ["*spe*", "*SPE*"],
        "bpftrace": ["*bpftrace*", "*.bt"],
    }
    found: dict[str, list[Path]] = {}
    if not run_dir.exists():
        return found
    for name, globs in patterns.items():
        files: list[Path] = []
        for glob in globs:
            files.extend(p for p in run_dir.rglob(glob) if p.is_file())
        found[name] = sorted(set(files))
    return found


def parse_lock_file(path: Path, limit: int) -> list[tuple[int, int, int, int, str, str]]:
    rows = []
    for line in path.read_text(errors="replace").splitlines():
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split(";")]
        if len(parts) < 6:
            continue
        vals = [number(p) for p in parts[:4]]
        if any(v is None for v in vals):
            continue
        rows.append((int(vals[0]), int(vals[1]), int(vals[2]), int(vals[3]), parts[4], parts[5]))
    rows.sort(key=lambda r: r[1], reverse=True)
    return rows[:limit]


def parse_mpstat(path: Path) -> dict[str, float | None]:
    try:
        data = json.loads(path.read_text(errors="replace"))
        stats = data["sysstat"]["hosts"][0]["statistics"]
    except Exception:  # noqa: BLE001
        return {}
    node_load = []
    cpu_load = []
    for item in stats:
        node_load.extend(item.get("node-load", []))
        cpu_load.extend(item.get("cpu-load", []))
    src = node_load or cpu_load
    out = {}
    for key in ("usr", "sys", "iowait", "soft", "idle"):
        vals = [number(x.get(key)) for x in src]
        vals = [v for v in vals if v is not None]
        out[key] = mean(vals) if vals else None
    return out


def clean_symbol(symbol: str) -> str:
    symbol = symbol.strip()
    symbol = symbol.split("+", 1)[0]
    symbol = COMPILER_SUFFIX_RE.sub("", symbol)
    return symbol


def parse_stack_file(path: Path) -> list[tuple[list[str], int]]:
    rows = []
    for line in path.read_text(errors="replace").splitlines():
        if not line.strip():
            continue
        stack, _, count_text = line.rpartition(" ")
        count = number(count_text)
        if not stack or count is None:
            continue
        symbols = [clean_symbol(s) for s in stack.split(";") if s]
        rows.append((symbols, int(count)))
    return rows


def top_stack_symbols(inv: dict[str, list[Path]], limit: int = 12) -> list[tuple[str, int, int]]:
    totals: dict[str, int] = defaultdict(int)
    leaves: dict[str, int] = defaultdict(int)
    ignored = {
        "arch_call_rest_init",
        "arch_cpu_idle",
        "cpu_startup_entry",
        "cpuidle_idle_call",
        "default_idle_call",
        "do_idle",
        "rest_init",
        "start_kernel",
        "swapper",
        "run",
        "el0_sync",
        "el0_sync_handler",
        "el0_svc",
        "el0_svc_common",
        "invoke_syscall",
    }
    for path in inv.get("flamegraph", []):
        if path.name != "flamegraph.stacks" or path.stat().st_size <= 0:
            continue
        for symbols, count in parse_stack_file(path):
            kernelish = [
                s
                for s in symbols
                if s
                and not s.startswith("[")
                and not s.startswith("mysql_")
                and s not in ignored
            ]
            for sym in set(kernelish):
                totals[sym] += count
            if kernelish:
                leaves[kernelish[-1]] += count
    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    return [(sym, samples, leaves.get(sym, 0)) for sym, samples in ranked[:limit]]


def source_subsystem(path: str) -> str:
    for prefix, label in SOURCE_SUBSYSTEM_HINTS:
        if path.startswith(prefix):
            return label
    return "kernel source"


def lookup_symbol_source(symbol: str, linux: Path, limit: int = 4) -> list[tuple[str, int, str]]:
    if not linux.exists():
        return []
    sym = clean_symbol(symbol)
    if not sym or sym in {"syscall", "do_el0_svc"}:
        return []
    cache_key = (str(linux.resolve()), sym)
    if cache_key in SOURCE_LOOKUP_CACHE:
        return SOURCE_LOOKUP_CACHE[cache_key][:limit]

    search_roots = [str(linux / d) for d in SOURCE_DIRS if (linux / d).exists()]
    pattern = rf"\b{re.escape(sym)}\s*\("
    try:
        proc = subprocess.run(
            ["rg", "-n", "--no-heading", "--glob", "*.{c,h,S}", pattern, *search_roots],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        SOURCE_LOOKUP_CACHE[cache_key] = []
        return []

    hits = []
    for line in proc.stdout.splitlines():
        path_text, sep, rest = line.partition(":")
        if not sep:
            continue
        lineno_text, sep, text = rest.partition(":")
        if not sep or not lineno_text.isdigit():
            continue
        path = Path(path_text)
        try:
            rel = str(path.relative_to(linux))
        except ValueError:
            rel = path_text
        text = text.strip()
        stripped = text.lstrip()
        score = 0
        if not stripped or stripped.startswith(("*", "/*", "//")):
            score -= 10
        is_signature = bool(re.search(rf"\b{re.escape(sym)}\s*\(", text)) and ";" not in text
        looks_like_definition = is_signature and not stripped.startswith(
            ("return ", "if ", "while ", "for ", "case ", "switch ", "err", "ret", "status")
        )
        if looks_like_definition:
            score += 20
        elif is_signature:
            score += 8
        if re.search(rf"\b{re.escape(sym)}\s*\([^;]*$", text):
            score += 4
        if rel.endswith((".c", ".S")):
            score += 3
        if rel.endswith(".h"):
            score -= 2
        if rel.startswith("arch/") and not rel.startswith("arch/arm64/"):
            score -= 6
        if rel.startswith(("fs/", "block/", "kernel/", "mm/", "net/")):
            score += 3
        if "/staging/" in rel or "/target/" in rel:
            score -= 4
        hits.append((score, rel, int(lineno_text), text))

    hits.sort(key=lambda h: (-h[0], h[1], h[2]))
    result = [(rel, lineno, text) for _score, rel, lineno, text in hits[: max(limit, 8)]]
    SOURCE_LOOKUP_CACHE[cache_key] = result
    return result[:limit]


def hot_source_correlations(
    stack_symbols: list[tuple[str, int, int]], linux: Path, limit: int = 10
) -> list[dict[str, object]]:
    rows = []
    for sym, inclusive, leaf in stack_symbols:
        hits = lookup_symbol_source(sym, linux, limit=1)
        if not hits:
            continue
        rel, lineno, text = hits[0]
        rows.append(
            {
                "symbol": sym,
                "inclusive": inclusive,
                "leaf": leaf,
                "path": rel,
                "line": lineno,
                "source": text,
                "subsystem": source_subsystem(rel),
            }
        )
    rows.sort(key=lambda r: -(int(r["inclusive"])))
    return rows[:limit]


def summarize_source_targets(
    correlations: list[dict[str, object]],
    limit: int = 3,
    link_base_dir: Path | None = None,
    linux: Path | None = None,
) -> str:
    seen = []
    for row in correlations:
        source_ref = f"{row['path']}:{row['line']}"
        if link_base_dir is not None and linux is not None:
            source_ref = local_file_link(source_ref, linux / str(row["path"]), link_base_dir, int(row["line"]))
        target = f"{row['subsystem']}:{row['symbol']}@{source_ref}"
        if target not in seen:
            seen.append(target)
    return ", ".join(seen[:limit]) or "none"


def extract_ops(benchmark: str) -> list[str]:
    tokens = benchmark.split("_")
    if tokens[:3] == ["bm", "min", "mysql"]:
        tokens = tokens[3:]
    if tokens[:3] == ["bm", "min", "rocks"]:
        tokens = tokens[3:]
    ops = []
    skip = {"missing"}
    for tok in tokens:
        if tok.isdigit() or tok in skip:
            continue
        if tok in SYSCALL_SOURCE_MAP and tok not in ops:
            ops.append(tok)
    return ops


def source_correlations(benchmark: str, linux: Path) -> list[tuple[str, str, str, bool]]:
    out = []
    for op in extract_ops(benchmark):
        for rel, func in SYSCALL_SOURCE_MAP.get(op, []):
            out.append((op, rel, func, (linux / rel).exists()))
    return out


def subsystem_hint(benchmark: str, inv: dict[str, list[Path]]) -> str:
    ops = set(extract_ops(benchmark))
    if ops & {"recvfrom", "sendto", "setsockopt"}:
        return "network/socket path"
    if ops & {"fsync", "fallocate", "pwrite64", "write"}:
        return "filesystem writeback/block path"
    if ops & {"openat", "newfstatat", "readlinkat", "getdents64", "faccessat2"}:
        return "VFS pathname/dentry/inode path"
    if ops & {"fcntl", "lseek", "pread64", "read"}:
        return "VFS file operation path"
    if any(p.name == "flamegraph.stacks" and p.stat().st_size > 0 for p in inv.get("flamegraph", [])):
        return "kernel hot path from flamegraph stacks"
    return "unknown kernel/user path"


def artifact_present(inv: dict[str, list[Path]], group: str) -> bool:
    return any(p.stat().st_size > 0 for p in inv.get(group, []))


def symbol_term_counts(stack_symbols: list[tuple[str, int, int]]) -> dict[str, int]:
    counts = {name: 0 for name in PATTERN_TERMS}
    for symbol, inclusive, _leaf in stack_symbols:
        for name, terms in PATTERN_TERMS.items():
            if any(term in symbol for term in terms):
                counts[name] += int(inclusive)
    return counts


def perf_pattern_classification(
    benchmark: str,
    inv: dict[str, list[Path]],
    stack_symbols: list[tuple[str, int, int]] | None = None,
) -> dict[str, object]:
    """Classify a run before patch selection using CSB, linux-perf, and patterns rules."""
    ops = set(extract_ops(benchmark))
    stack_symbols = stack_symbols if stack_symbols is not None else top_stack_symbols(inv)
    counts = symbol_term_counts(stack_symbols)
    has_c2c = any("c2c" in p.name.lower() and p.stat().st_size > 0 for files in inv.values() for p in files)
    has_lock = artifact_present(inv, "lock")
    notes = []

    if ops & {"fsync"}:
        classification = "sync/flush serialization"
        pattern_result = "outside performance-patterns CPU/cache-line catalog unless lock/c2c evidence also appears"
        patch_direction = "fsync/writeback/flush batching, journal/flush policy, or fast-commit backport"
        confidence = "medium" if counts["flush"] or artifact_present(inv, "iostat") else "low-medium"
    elif ops & {"fallocate"}:
        classification = "ext4/VFS metadata path"
        pattern_result = "no direct CPU-cache pattern; optimize filesystem metadata work per syscall"
        patch_direction = "ext4 fallocate transaction/path trimming"
        confidence = "medium" if counts["ext4"] or counts["flush"] else "low-medium"
    elif ops & {"faccessat2", "newfstatat", "openat", "readlinkat", "getdents64"}:
        classification = "VFS pathname/dentry/inode path"
        pattern_result = "no direct pattern match; reduce lookup/refcount/permission overhead"
        patch_direction = "VFS pathname/access hotpath reduction"
        confidence = "medium" if counts["path"] else "low-medium"
    elif ops & {"pread64", "pwrite64", "read", "write", "lseek", "fcntl"}:
        classification = "VFS file operation/read-write iterator path"
        pattern_result = "no direct pattern match; reduce generic iterator, copy, fcntl, or file-operation overhead"
        patch_direction = "sync read/write iterator specialization or file-operation fastpath"
        confidence = "medium" if counts["rw"] else "low-medium"
    elif ops & {"recvfrom", "sendto", "setsockopt"}:
        classification = "socket/TCP syscall path"
        pattern_result = "no direct pattern match unless wakeup/futex contention is visible"
        patch_direction = "socket recv/send batching or timestamp/path trimming"
        confidence = "medium" if counts["net"] else "low-medium"
    elif counts["wakeup"]:
        classification = "scheduler/wakeup overhead"
        pattern_result = "possible CV/futex thundering herd; needs context-switch or futex trace support"
        patch_direction = "reduce wakeup fan-out, batch work, or use precise wakeups"
        confidence = "medium"
    elif counts["mutex"]:
        classification = "mutex/OSQ contention"
        pattern_result = "possible mutex-to-rwlock only if source critical section is read-mostly"
        patch_direction = "lock granularity or reader/writer split after lock-stat/source proof"
        confidence = "medium" if has_lock else "low"
    elif counts["spin"]:
        classification = "spinlock/cache-line contention"
        pattern_result = "possible TTAS/spinlock contention; needs annotate or lock-stat proof"
        patch_direction = "reduce contended lock frequency or redesign lock handoff"
        confidence = "medium" if has_lock or has_c2c else "low"
    elif counts["accounting"] and has_c2c:
        classification = "shared accounting/cache-line pressure"
        pattern_result = "possible per-CPU stats if c2c proves true sharing on a counter"
        patch_direction = "per-CPU or batched accounting"
        confidence = "medium"
    elif counts["flush"]:
        classification = "sync/flush serialization"
        pattern_result = "outside performance-patterns CPU/cache-line catalog: flush/journal/block path dominates"
        patch_direction = "fsync/writeback/flush batching, journal/flush policy, or fast-commit backport"
        confidence = "medium"
    else:
        classification = "unresolved saved-profile bottleneck"
        pattern_result = "no robust performance-patterns match from saved artifacts"
        patch_direction = "collect focused perf stat/report/annotate plus c2c or lock-stat if contention is suspected"
        confidence = "low"

    if counts["flush"] and "flush" not in classification:
        notes.append("flush/journal/block symbols are present as supporting evidence")
    if counts["wakeup"] and "wakeup" not in classification:
        notes.append("wakeup/scheduler symbols are present but are not the primary classifier")
    if counts["mutex"] and "mutex" not in classification:
        notes.append("mutex/OSQ symbols are present; promote only with lock-stat and read-mostly source proof")
    if counts["spin"] and "spinlock" not in classification:
        notes.append("spin/cmpxchg symbols are present; promote only with annotate or lock-stat proof")
    if counts["accounting"] and not has_c2c:
        notes.append("atomic/per-CPU-looking symbols need c2c/annotate proof before a per-CPU-stats proposal")
    if not has_c2c:
        notes.append("false sharing and true-sharing fixes are unconfirmed without perf c2c/HITM evidence")
    if not has_lock:
        notes.append("lock-pattern matches are candidates only without lock-stat/perf-lock evidence")

    return {
        "classification": classification,
        "pattern_result": pattern_result,
        "patch_direction": patch_direction,
        "confidence": confidence,
        "term_counts": counts,
        "notes": notes,
        "has_c2c": has_c2c,
        "has_lock": has_lock,
    }


def inflection_summaries(records: list[dict[str, object]]) -> list[str]:
    by_exec: dict[tuple[object, object, object, object], list[dict[str, object]]] = defaultdict(list)
    for rec in records:
        key = tuple(rec.get(k, "") for k in ("execution_type", "nb_threads", "noise", "initial_size"))
        by_exec[key].append(rec)
    notes = []
    for key, vals in by_exec.items():
        vals = [v for v in vals if v.get("throughput_min") is not None]
        if not vals:
            continue
        vals.sort(key=lambda r: number(r.get("container_cnt")) or 0)
        baseline = vals[0]
        peak = max(vals, key=lambda r: number(r.get("throughput_min")) or 0)
        last = vals[-1]
        base_thr = number(baseline.get("throughput_min"))
        peak_thr = number(peak.get("throughput_min"))
        last_thr = number(last.get("throughput_min"))
        if base_thr is None or peak_thr is None or last_thr is None:
            continue
        worst_pair = None
        for prev, cur in zip(vals, vals[1:]):
            prev_thr = number(prev.get("throughput_min"))
            cur_thr = number(cur.get("throughput_min"))
            if prev_thr and cur_thr is not None:
                drop = 100.0 * (1.0 - (cur_thr / prev_thr))
                if worst_pair is None or drop > worst_pair[0]:
                    worst_pair = (drop, prev, cur)
        exec_type = key[0]
        peak_drop = 100.0 * (1.0 - last_thr / peak_thr) if peak_thr else 0.0
        success_start = number(baseline.get("univ_succ_percent"))
        success_last = number(last.get("univ_succ_percent"))
        latency_start = number(baseline.get("univ_avg"))
        latency_last = number(last.get("univ_avg"))
        cpu_note = f"sys {fmt(number(last.get('sys')))}%, idle {fmt(number(last.get('idle')))}%"
        parts = [
            f"{exec_type}: baseline count {baseline.get('container_cnt')} throughput {fmt(base_thr)}",
            f"peak count {peak.get('container_cnt')} throughput {fmt(peak_thr)}",
            f"last count {last.get('container_cnt')} throughput {fmt(last_thr)}",
            f"drop from peak {fmt(max(0.0, peak_drop))}%",
            cpu_note,
        ]
        if worst_pair and worst_pair[0] > 0:
            parts.append(
                "largest adjacent drop {drop}% from count {a} to {b}".format(
                    drop=fmt(worst_pair[0]),
                    a=worst_pair[1].get("container_cnt"),
                    b=worst_pair[2].get("container_cnt"),
                )
            )
        if success_start is not None and success_last is not None:
            parts.append(f"success {fmt(success_start)}% -> {fmt(success_last)}%")
        if latency_start and latency_last is not None:
            parts.append(f"latency {fmt(latency_start)} -> {fmt(latency_last)} ({latency_last / latency_start:.2f}x)")
        notes.append("; ".join(parts))
    return notes


def scaling_table(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    if not rows:
        return []
    dims = [k for k in ("execution_type", "nb_threads", "noise", "initial_size", "container_cnt") if k in rows[0]]
    metric = next((c for c in ("throughput_min", "throughput_max", "univ_succ_percent", "univ_avg") if c in rows[0]), None)
    groups = grouped(rows, dims)
    records = []
    for key, grows in groups.items():
        rec = {dim: key[i] for i, dim in enumerate(dims)}
        for col in ("throughput_min", "throughput_max"):
            vals = [number(r.get(col)) for r in grows]
            vals = [v for v in vals if v is not None]
            rec[col] = sum(vals) if vals else None
        rec["univ_avg"] = avg(grows, "univ_avg")
        rec["univ_succ_percent"] = avg(grows, "univ_succ_percent")
        rec["sys"] = avg(grows, "sys_c0")
        rec["iowait"] = avg(grows, "iowait_c0")
        rec["idle"] = avg(grows, "idle_c0")
        rec["_metric"] = metric
        records.append(rec)
    records.sort(key=lambda r: (str(r.get("execution_type", "")), number(r.get("container_cnt")) or 0))
    baselines = {}
    for rec in records:
        base_key = tuple((k, rec.get(k)) for k in ("execution_type", "nb_threads", "noise", "initial_size") if k in rec)
        val = rec.get("throughput_min")
        if val is not None and base_key not in baselines:
            baselines[base_key] = val
    for rec in records:
        base_key = tuple((k, rec.get(k)) for k in ("execution_type", "nb_threads", "noise", "initial_size") if k in rec)
        base = baselines.get(base_key)
        val = rec.get("throughput_min")
        rec["throughput_vs_base_pct"] = (100.0 * val / base) if base and val is not None else None
    return records


def scaling_capacity_table(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    if not rows:
        return []
    dims = [k for k in ("execution_type", "nb_threads", "noise", "initial_size", "container_cnt") if k in rows[0]]
    groups = grouped(rows, dims)
    records = []
    for key, grows in groups.items():
        rec = {dim: key[i] for i, dim in enumerate(dims)}
        vals = [number(r.get("throughput_min")) for r in grows]
        vals = [v for v in vals if v is not None]
        rec["throughput_min"] = sum(vals) if vals else None
        rec["univ_avg"] = avg(grows, "univ_avg")
        rec["univ_succ_percent"] = avg(grows, "univ_succ_percent")
        records.append(rec)
    records.sort(key=lambda r: (str(r.get("execution_type", "")), number(r.get("container_cnt")) or 0))
    return records


def monitor_strength(inv: dict[str, list[Path]]) -> tuple[int, str]:
    signals = []
    score = 0
    for name, points in (
        ("lock", 3),
        ("bpftrace", 3),
        ("perf", 2),
        ("flamegraph", 2),
        ("spe", 2),
        ("mpstat", 1),
        ("iostat", 1),
    ):
        files = inv.get(name, [])
        nonempty = [p for p in files if p.stat().st_size > 0]
        if nonempty:
            score += points
            signals.append(f"{name}:{len(nonempty)}")
        elif files:
            signals.append(f"{name}:empty")
    return score, ", ".join(signals) or "none"


def run_degradation_summary(
    run: dict[str, Path | str],
    linux: Path | None = None,
    link_base_dir: Path | None = None,
) -> dict[str, object]:
    base = str(run["base"])
    system, benchmark, timestamp = run_parts(base)
    _fields, rows = read_csv_rows(run["csv"])
    table = scaling_capacity_table(rows)
    inv = monitor_inventory(run["dir"])
    mon_score, mon_text = monitor_strength(inv)
    linux = linux or Path("deps/linux")
    source_targets = hot_source_correlations(top_stack_symbols(inv, limit=8), linux, limit=5)
    classifier = perf_pattern_classification(benchmark, inv)

    by_exec: dict[str, list[dict[str, object]]] = defaultdict(list)
    for rec in table:
        by_exec[str(rec.get("execution_type", "unknown"))].append(rec)

    best_exec = "n/a"
    best_peak = None
    worst_rec = None
    worst_degradation = None
    success_drop = None
    latency_ratio = None
    baseline_count = "n/a"

    for execution_type, records in by_exec.items():
        records = [r for r in records if r.get("throughput_min") is not None]
        if not records:
            continue
        records.sort(key=lambda r: number(r.get("container_cnt")) or 0)
        baseline = records[0]
        peak = max(number(r.get("throughput_min")) or 0 for r in records)
        last = records[-1]
        last_thr = number(last.get("throughput_min"))
        if peak <= 0 or last_thr is None:
            continue
        degradation = max(0.0, 100.0 * (1.0 - (last_thr / peak)))
        base_success = number(baseline.get("univ_succ_percent"))
        last_success = number(last.get("univ_succ_percent"))
        this_success_drop = (base_success - last_success) if base_success is not None and last_success is not None else None
        base_lat = number(baseline.get("univ_avg"))
        last_lat = number(last.get("univ_avg"))
        this_latency_ratio = (last_lat / base_lat) if base_lat and last_lat is not None else None
        if worst_degradation is None or degradation > worst_degradation:
            best_exec = execution_type
            best_peak = peak
            worst_rec = last
            worst_degradation = degradation
            success_drop = this_success_drop
            latency_ratio = this_latency_ratio
            baseline_count = baseline.get("container_cnt", "n/a")

    worst_count = worst_rec.get("container_cnt", "n/a") if worst_rec else "n/a"
    worst_thr = number(worst_rec.get("throughput_min")) if worst_rec else None
    worst_degradation = worst_degradation if worst_degradation is not None else 0.0

    score = worst_degradation
    if success_drop:
        score += min(15.0, max(0.0, success_drop))
    if latency_ratio and latency_ratio > 1.0:
        score += min(15.0, (latency_ratio - 1.0) * 5.0)
    score += min(15.0, mon_score * 2.5)

    if worst_degradation >= 80 and mon_score >= 4:
        patch_conf = "high"
    elif worst_degradation >= 60 and mon_score >= 2:
        patch_conf = "medium"
    elif worst_degradation >= 40:
        patch_conf = "low-medium"
    else:
        patch_conf = "low"

    if worst_degradation >= 80:
        potential = "large"
    elif worst_degradation >= 60:
        potential = "moderate-large"
    elif worst_degradation >= 40:
        potential = "moderate"
    else:
        potential = "limited"

    if not table:
        note = "No parseable scaling rows; cannot rank confidently."
    elif mon_score == 0:
        note = "Scaling signal only; monitor evidence missing or empty."
    elif mon_score < 3:
        note = "Monitor evidence is partial; needs targeted perf/lock/bpftrace before patch claims."
    else:
        note = "Benchmark degradation has matching monitor coverage; good candidate for deeper source correlation."

    return {
        "base": base,
        "system": system,
        "benchmark": benchmark,
        "timestamp": timestamp,
        "execution_type": best_exec,
        "baseline_count": baseline_count,
        "worst_count": worst_count,
        "peak_throughput": best_peak,
        "worst_throughput": worst_thr,
        "degradation": worst_degradation,
        "success_drop": success_drop,
        "latency_ratio": latency_ratio,
        "monitor_score": mon_score,
        "monitor_text": mon_text,
        "source_targets": summarize_source_targets(source_targets, link_base_dir=link_base_dir, linux=linux),
        "source_target_count": len(source_targets),
        "classification": classifier["classification"],
        "pattern_result": classifier["pattern_result"],
        "patch_direction": classifier["patch_direction"],
        "classifier_confidence": classifier["confidence"],
        "potential": potential,
        "patch_confidence": patch_conf,
        "score": score,
        "note": note,
    }


def write_summary_report(args: argparse.Namespace) -> str:
    results_dir = Path(args.results_dir)
    linux = Path(args.linux)
    complete, incomplete = collect_runs(results_dir)
    summaries = [run_degradation_summary(run, linux, link_base_dir=results_dir) for run in complete]
    summaries.sort(key=lambda r: (float(r["score"]), float(r["degradation"])), reverse=True)

    lines = [
        "# CSB Cross-Run Scaling Summary",
        "",
        f"- Results directory: `{results_dir}`",
        f"- Complete analyzed runs: {len(complete)}",
        f"- Incomplete runs skipped: {len(incomplete)}",
        "",
        "This summary ranks independently analyzed runs by observed many-core scaling degradation and the strength of supporting monitor evidence. It is a triage ranking for kernel patch investigation, not proof that a patch will improve performance.",
        "",
    ]
    if incomplete:
        lines += ["## Skipped Incomplete Runs", ""]
        for run, missing in incomplete:
            lines.append(f"- `{run['base']}` missing: {', '.join(missing)}")
        lines.append("")

    lines += [
        "## Ranked Patch-Investigation Candidates",
        "",
        "| rank | run | report | result html | benchmark | execution | count range | degradation from peak | success drop | latency ratio | monitor evidence | linux-perf/pattern class | pattern result | patch direction | source targets | scaling potential | patch confidence |",
        "|---:|---|---|---|---|---|---|---:|---:|---:|---|---|---|---|---|---|---|",
    ]
    for idx, rec in enumerate(summaries, start=1):
        count_range = f"{rec['baseline_count']} -> {rec['worst_count']}"
        lat = rec["latency_ratio"]
        lines.append(
            "| {rank} | `{run}` | {report} | {result_html} | `{benchmark}` | {execution} | {count_range} | {deg} | {succ} | {lat} | {mon} | {classify} | {pattern} | {direction} | {source} | {potential} | {conf} |".format(
                rank=idx,
                run=rec["base"],
                report=local_file_link("analysis html", results_dir / f"{rec['base']}_csb-analysis.html", results_dir),
                result_html=local_file_link("result html", results_dir / f"{rec['base']}.html", results_dir),
                benchmark=rec["benchmark"],
                execution=rec["execution_type"],
                count_range=count_range,
                deg=fmt(rec["degradation"]),
                succ=fmt(rec["success_drop"]),
                lat="n/a" if lat is None else f"{lat:.2f}x",
                mon=rec["monitor_text"],
                classify=rec["classification"],
                pattern=rec["pattern_result"],
                direction=rec["patch_direction"],
                source=rec["source_targets"],
                potential=rec["potential"],
                conf=rec["patch_confidence"],
            )
        )

    lines += [
        "",
        "## Interpretation Guide",
        "",
        "- **Degradation from peak** compares the highest observed throughput in a run/execution type with the largest-count result for that same execution type.",
        "- **Scaling potential** estimates how much room exists to improve many-core scaling if the bottleneck is in a kernel path.",
        "- **Patch confidence** combines the benchmark inflection with available monitor evidence. It should be downgraded during detailed analysis if perf/lock/bpftrace evidence does not map to a plausible kernel path.",
        "- **linux-perf/pattern class** is a first-pass classifier that combines benchmark syscall shape, saved perf/flamegraph symbols, and performance-pattern trigger rules. It may rule out CPU/cache-line patterns even for severe degradation.",
        "- **Source targets** are top flamegraph symbols resolved against `deps/linux`; links point to local source files and are upstream references unless the measured kernel source is an exact match.",
        "- **Report** links open the generated detailed HTML report; **result html** links open the original CSB plot/report HTML for that run.",
        "- Keep native and container results separate until explicitly comparing overheads.",
        "",
        "## Per-Run Notes",
        "",
    ]
    for rec in summaries:
        base_name = str(rec["base"])
        lines += [
            f"### {base_name}",
            "",
            f"- Benchmark: `{rec['benchmark']}`",
            f"- Worst scaling dimension: {rec['execution_type']} count {rec['baseline_count']} -> {rec['worst_count']}",
            f"- Degradation from peak: {fmt(rec['degradation'])}%",
            f"- Potential for kernel scaling improvement: {rec['potential']}",
            f"- Confidence that a proposed kernel-scaling patch would help: {rec['patch_confidence']}",
            f"- linux-perf/performance-patterns class: {rec['classification']} ({rec['pattern_result']})",
            f"- First-pass patch direction: {rec['patch_direction']}",
            f"- Detailed report: {local_file_link('analysis html', results_dir / f'{base_name}_csb-analysis.html', results_dir)}",
            f"- Original result HTML: {local_file_link('result html', results_dir / f'{base_name}.html', results_dir)}",
            f"- Hot source targets: {rec['source_targets']}",
            f"- Evidence note: {rec['note']}",
            "",
        ]
    return "\n".join(lines)


def write_report(args: argparse.Namespace, only_run: dict[str, Path | str] | None = None) -> str:
    results_dir = Path(args.results_dir)
    linux = Path(args.linux)
    lines = [
        "# CSB Results Analysis",
        "",
        f"- Results directory: `{results_dir}`",
        f"- Linux source: `{linux}` ({'present' if linux.exists() else 'missing'})",
        "",
    ]
    if only_run is None:
        complete, incomplete = collect_runs(results_dir)
        complete_items = [(run, []) for run in complete]
    else:
        complete = [only_run]
        incomplete = []
        complete_items = [(only_run, [])]
    lines += [f"- Complete runs: {len(complete)}", f"- Incomplete runs: {len(incomplete)}", ""]
    if incomplete:
        lines.append("## Incomplete Runs")
        lines.append("")
        for run, missing in incomplete:
            lines.append(f"- `{run['base']}` missing: {', '.join(missing)}")
        lines.append("")
    for run, _ in complete_items:
        base = run["base"]
        system, benchmark, timestamp = run_parts(base)
        fields, rows = read_csv_rows(run["csv"])
        monitors, apps = summarize_config(run["json"])
        inv = monitor_inventory(run["dir"])
        lines += [
            f"## {base}",
            "",
            f"- System: `{system}`",
            f"- Benchmark: `{benchmark}`",
            f"- Timestamp: `{timestamp}`",
            f"- Original result HTML: {local_file_link(f'{base}.html', results_dir / f'{base}.html', results_dir)}",
            f"- Generated analysis HTML: {local_file_link(f'{base}_csb-analysis.html', results_dir / f'{base}_csb-analysis.html', results_dir)}",
            f"- Configured monitors: {monitors}",
            f"- Applications: {apps}",
            f"- CSV rows: {len(rows)}",
        ]
        if rows:
            sample = rows[0]
            for col in ("kernel", "architecture", "hostname", "cgroup", "Allowed CPUs"):
                if sample.get(col):
                    lines.append(f"- {col}: `{sample[col]}`")
        lines.append("")
        lines.append("### Scaling Summary")
        lines.append("")
        table = scaling_table(rows)
        if table:
            lines.append("Throughput values are aggregate capacity across execution units for the same parameter point.")
            lines.append("")
            lines.append("| execution_type | containers | throughput_min | vs baseline | univ_avg | success % | sys % | iowait % | idle % |")
            lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
            for rec in table:
                lines.append(
                    "| {execution_type} | {container_cnt} | {thr} | {base} | {lat} | {succ} | {sys} | {iowait} | {idle} |".format(
                        execution_type=rec.get("execution_type", "n/a"),
                        container_cnt=rec.get("container_cnt", "n/a"),
                        thr=fmt(rec.get("throughput_min")),
                        base=fmt(rec.get("throughput_vs_base_pct")),
                        lat=fmt(rec.get("univ_avg")),
                        succ=fmt(rec.get("univ_succ_percent")),
                        sys=fmt(rec.get("sys")),
                        iowait=fmt(rec.get("iowait")),
                        idle=fmt(rec.get("idle")),
                    )
                )
        else:
            lines.append("No parseable scaling rows found.")
        lines.append("")
        inflections = inflection_summaries(table)
        if inflections:
            lines.append("### Inflection Points")
            lines.append("")
            for note in inflections:
                lines.append(f"- {note}")
            lines.append("")
        lines.append("### Monitor Inventory")
        lines.append("")
        for name, files in inv.items():
            nonempty = [p for p in files if p.stat().st_size > 0]
            lines.append(f"- {name}: {len(files)} files, {len(nonempty)} non-empty")
        lines.append("")
        lock_files = [p for p in inv.get("lock", []) if p.name == "lock-contention.csv" and p.stat().st_size > 0]
        if lock_files:
            lines.append("### Top Lock Contention Callers")
            lines.append("")
            lines.append("| caller | type | contended | total wait | avg wait | file |")
            lines.append("|---|---|---:|---:|---:|---|")
            lock_rows = []
            for path in lock_files:
                for row in parse_lock_file(path, args.top_locks):
                    lock_rows.append((*row, path))
            lock_rows.sort(key=lambda r: r[1], reverse=True)
            for contended, total, _max_wait, avg_wait, typ, caller, path in lock_rows[: args.top_locks]:
                rel = path.relative_to(results_dir)
                lines.append(f"| `{caller}` | {typ} | {contended} | {total} | {avg_wait} | `{rel}` |")
            lines.append("")
        mpstat_files = [p for p in inv.get("mpstat", []) if p.name == "mpstat.json" and p.stat().st_size > 0]
        if mpstat_files:
            vals = [parse_mpstat(p) for p in mpstat_files[: min(20, len(mpstat_files))]]
            lines.append("### mpstat Snapshot")
            lines.append("")
            for key in ("usr", "sys", "iowait", "soft", "idle"):
                samples = [v.get(key) for v in vals if v.get(key) is not None]
                lines.append(f"- avg {key}: {fmt(mean(samples) if samples else None)}")
            lines.append("")
        stack_symbols = top_stack_symbols(inv)
        if stack_symbols:
            lines.append("### Flamegraph Stack Hot Symbols")
            lines.append("")
            lines.append("| symbol | inclusive samples | leaf samples |")
            lines.append("|---|---:|---:|")
            for sym, inclusive, leaf in stack_symbols:
                lines.append(f"| `{sym}` | {inclusive} | {leaf} |")
            lines.append("")

        classifier = perf_pattern_classification(benchmark, inv, stack_symbols)
        term_counts = classifier["term_counts"]
        nonzero_terms = [
            f"{name}:{value}" for name, value in sorted(term_counts.items()) if value
        ]
        lines.append("### linux-perf And Performance-Patterns First-Pass Classification")
        lines.append("")
        lines.append(
            "This first-pass classifier combines the CSB scaling shape, benchmark syscall family, saved perf/flamegraph symbols, and performance-pattern trigger rules before selecting a patch direction."
        )
        lines.append("")
        lines.append(f"- Classification: {classifier['classification']}")
        lines.append(f"- Performance-patterns result: {classifier['pattern_result']}")
        lines.append(f"- Patch direction: {classifier['patch_direction']}")
        lines.append(f"- Classifier confidence: {classifier['confidence']}")
        lines.append(
            f"- Specialized evidence present: c2c={'yes' if classifier['has_c2c'] else 'no'}, lock-stat/perf-lock={'yes' if classifier['has_lock'] else 'no'}"
        )
        lines.append(f"- Pattern symbol buckets: {', '.join(nonzero_terms) if nonzero_terms else 'none'}")
        if classifier["notes"]:
            lines.append("- Classifier caveats:")
            for note in classifier["notes"]:
                lines.append(f"  - {note}")
        lines.append("")

        lines.append("### Source Correlation")
        lines.append("")
        hot_sources = hot_source_correlations(stack_symbols, linux, limit=12)
        if hot_sources:
            lines.append("Hot symbols from `flamegraph.stacks` resolved against `deps/linux`:")
            lines.append("")
            lines.append("| symbol | subsystem | source | line | samples | source text |")
            lines.append("|---|---|---|---:|---:|---|")
            for row in hot_sources:
                source_text = str(row["source"]).replace("|", "\\|")
                source_link = local_file_link(
                    f"{row['path']}:{row['line']}",
                    linux / str(row["path"]),
                    results_dir,
                    int(row["line"]),
                )
                lines.append(
                    "| `{symbol}` | {subsystem} | {source} | {line} | {samples} | `{text}` |".format(
                        symbol=row["symbol"],
                        subsystem=row["subsystem"],
                        source=source_link,
                        line=row["line"],
                        samples=row["inclusive"],
                        text=source_text[:160],
                    )
                )
            lines.append("")
        elif stack_symbols:
            lines.append(
                "Hot flamegraph symbols were present, but no exact source hits were found in `deps/linux` for the top symbols."
            )
            lines.append("")

        correlations = source_correlations(benchmark, linux)
        if correlations:
            lines.append(
                "Benchmark-name syscall/source pivots:"
            )
            lines.append("")
            lines.append("| operation | source file | function/path | present |")
            lines.append("|---|---|---|---|")
            for op, rel, func, present in correlations:
                source = local_file_link(rel, linux / rel, results_dir) if present else f"`{rel}`"
                lines.append(f"| `{op}` | {source} | `{func}` | {'yes' if present else 'no'} |")
        else:
            lines.append(
                "No syscall/source mapping was inferred from the benchmark name; use the hot symbols above for manual `rg`/`git grep` correlation."
            )
        lines.append("")

        mon_score, mon_text = monitor_strength(inv)
        degradation = run_degradation_summary(run, linux)
        subsystem = subsystem_hint(benchmark, inv)
        hot_target_text = summarize_source_targets(hot_sources, link_base_dir=results_dir, linux=linux)
        lines += [
            "### Hypothesis",
            "",
            (
                f"- Likely bottleneck area: {subsystem}; first-pass linux-perf/pattern class is {classifier['classification']}. Observed worst degradation from peak is "
                f"{fmt(degradation['degradation'])}% for {degradation['execution_type']} at count "
                f"{degradation['worst_count']}; monitor evidence score is {mon_score} ({mon_text})."
            ),
            f"- Performance-patterns interpretation: {classifier['pattern_result']}.",
            f"- Hot source targets from flamegraph/source correlation: {hot_target_text}.",
        ]
        if mon_score >= 4 and degradation["degradation"] >= 60:
            lines.append(
                "- Confidence: medium to high for a kernel-scaling investigation, because the throughput inflection has matching monitor coverage."
            )
        elif mon_score > 0:
            lines.append(
                "- Confidence: low to medium; the benchmark signal is useful, but more targeted perf/lock/bpftrace evidence is needed before claiming a kernel root cause."
            )
        else:
            lines.append(
                "- Confidence: low; this report has benchmark scaling but little monitor evidence."
            )
        lines += [
            "",
            "### Patch Direction",
            "",
            (
                f"- Target subsystem: {subsystem}. First-pass patch direction: {classifier['patch_direction']}. Start with the hot source targets and mapped files/functions above, "
                "then validate with targeted perf/lock/bpftrace at baseline, peak, and largest-count points."
            ),
            "- Candidate change shape: follow the classifier's subsystem direction first; use TTAS, rwlock, false-sharing, or per-CPU-stats fixes only when the required annotate, lock-stat, or c2c evidence confirms that named pattern.",
            "- Expected CSB improvement: higher aggregate `throughput_min`, smaller drop from peak at high counts, stable `univ_succ_percent`, and no latency regression in `univ_avg`.",
            "- Validation reruns: repeat the smallest count, peak count, largest count, and the largest adjacent-drop pair for the affected execution type; keep native and container runs separate.",
            "- Risks to watch: fairness, memory growth, writeback ordering, socket semantics, cgroup accounting, and architecture-specific behavior on aarch64.",
            "",
        ]
    return "\n".join(lines)


def resolve_out_path(template: str, run: dict[str, Path | str]) -> Path:
    base = str(run["base"])
    system, benchmark, timestamp = run_parts(base)
    return Path(
        template.format(
            base=safe_name(base),
            run_prefix=safe_name(run_prefix(base)),
            system=safe_name(system),
            benchmark=safe_name(benchmark),
            timestamp=safe_name(timestamp),
        )
    )


def main() -> None:
    args = parse_args()
    if args.out == "-":
        report = write_report(args)
        print(report)
    elif "{" in args.out:
        complete, incomplete = collect_runs(Path(args.results_dir))
        if incomplete:
            print(f"Skipping {len(incomplete)} incomplete run(s)")
        if not complete:
            raise SystemExit("No complete runs found")
        for run in complete:
            report = write_report(args, only_run=run)
            out = resolve_out_path(args.out, run)
            write_markdown_and_html(out, report, not args.no_html)
            print(out)
        if args.summary_out:
            summary_out = Path(args.summary_out)
            write_markdown_and_html(summary_out, write_summary_report(args), not args.no_html)
            print(summary_out)
    else:
        report = write_report(args)
        out = Path(args.out)
        write_markdown_and_html(out, report, not args.no_html)
        print(out)
        if args.summary_out:
            summary_out = Path(args.summary_out)
            write_markdown_and_html(summary_out, write_summary_report(args), not args.no_html)
            print(summary_out)


if __name__ == "__main__":
    main()
