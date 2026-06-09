#!/usr/bin/env python3
"""Generate a first-pass CSB result analysis report."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from statistics import mean


RUN_RE = re.compile(r"^(?P<prefix>.+?)_(?P<date>\d{8})_(?P<time>\d{6})_(?P<usec>\d{6})$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_dir", nargs="?", default="results")
    parser.add_argument("--out", default="-", help="Markdown output path, or '-' for stdout")
    parser.add_argument("--linux", default="deps/linux", help="Linux source directory to reference")
    parser.add_argument("--top-locks", type=int, default=8)
    parser.add_argument("--top-monitor-files", type=int, default=80)
    return parser.parse_args()


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


def discover_runs(results_dir: Path):
    bases = set()
    for p in results_dir.iterdir() if results_dir.exists() else []:
        if p.is_dir():
            bases.add(p.name)
        elif p.suffix in {".json", ".html", ".csv"}:
            bases.add(p.stem)
    for base in sorted(bases):
        yield {
            "base": base,
            "dir": results_dir / base,
            "json": results_dir / f"{base}.json",
            "html": results_dir / f"{base}.html",
            "csv": results_dir / f"{base}.csv",
        }


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
        "lock": ["lock-contention.csv", "lock-contention.errors", "perf-lock.log"],
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


def scaling_table(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    if not rows:
        return []
    dims = [k for k in ("execution_type", "nb_threads", "noise", "initial_size", "container_cnt") if k in rows[0]]
    metric = next((c for c in ("throughput_min", "throughput_max", "univ_succ_percent", "univ_avg") if c in rows[0]), None)
    groups = grouped(rows, dims)
    records = []
    for key, grows in groups.items():
        rec = {dim: key[i] for i, dim in enumerate(dims)}
        rec["throughput_min"] = avg(grows, "throughput_min")
        rec["throughput_max"] = avg(grows, "throughput_max")
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


def write_report(args: argparse.Namespace) -> str:
    results_dir = Path(args.results_dir)
    linux = Path(args.linux)
    lines = [
        "# CSB Results Analysis",
        "",
        f"- Results directory: `{results_dir}`",
        f"- Linux source: `{linux}` ({'present' if linux.exists() else 'missing'})",
        "",
    ]
    complete = []
    incomplete = []
    for run in discover_runs(results_dir):
        missing = [k for k in ("dir", "json", "html", "csv") if not run[k].exists()]
        (incomplete if missing else complete).append((run, missing))
    lines += [f"- Complete runs: {len(complete)}", f"- Incomplete runs: {len(incomplete)}", ""]
    if incomplete:
        lines.append("## Incomplete Runs")
        lines.append("")
        for run, missing in incomplete:
            lines.append(f"- `{run['base']}` missing: {', '.join(missing)}")
        lines.append("")
    for run, _ in complete:
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
        lines += [
            "### Source Correlation TODO",
            "",
            "- Search `deps/linux` for the top symbols/callers above after stripping offsets and compiler suffixes.",
            "- Map the benchmark inflection point to the matching monitor path dimensions.",
            "- State whether the Linux source tree matches the measured kernel or is only an upstream reference.",
            "",
            "### Patch Direction TODO",
            "",
            "- Identify the smallest kernel change likely to reduce the observed many-core bottleneck.",
            "- Include affected files/functions, expected CSB metric improvement, risk, and validation reruns.",
            "",
        ]
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    report = write_report(args)
    if args.out == "-":
        print(report)
    else:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report)
        print(out)


if __name__ == "__main__":
    main()
