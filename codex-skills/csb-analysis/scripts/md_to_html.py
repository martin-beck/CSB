#!/usr/bin/env python3
"""Render CSB analysis Markdown files to adjacent standalone HTML files."""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("markdown", nargs="+", help="Markdown file(s) to render")
    parser.add_argument("--out", help="HTML output path; only valid for one input")
    return parser.parse_args()


def inline(text: str) -> str:
    placeholders: list[str] = []

    def stash(value: str) -> str:
        placeholders.append(value)
        return f"\x00{len(placeholders) - 1}\x00"

    escaped = html.escape(text, quote=False)
    escaped = re.sub(r"`([^`]+)`", lambda m: stash(f"<code>{m.group(1)}</code>"), escaped)
    escaped = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda m: stash(f'<a href="{html.escape(m.group(2), quote=True)}">{m.group(1)}</a>'),
        escaped,
    )
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    for i, value in enumerate(placeholders):
        escaped = escaped.replace(f"\x00{i}\x00", value)
    return escaped


def table_row(line: str, header: bool = False) -> str:
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    tag = "th" if header else "td"
    return "<tr>" + "".join(f"<{tag}>{inline(c)}</{tag}>" for c in cells) + "</tr>"


def render_markdown(text: str) -> str:
    out: list[str] = []
    in_ul = False
    in_ol = False
    in_code = False
    in_table = False
    para: list[str] = []
    lines = text.splitlines()
    i = 0

    def close_para() -> None:
        nonlocal para
        if para:
            out.append(f"<p>{inline(' '.join(para))}</p>")
            para = []

    def close_lists() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False

    def close_table() -> None:
        nonlocal in_table
        if in_table:
            out.append("</tbody></table>")
            in_table = False

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            close_para()
            close_lists()
            close_table()
            if in_code:
                out.append("</code></pre>")
                in_code = False
            else:
                lang = stripped[3:].strip()
                cls = f' class="language-{html.escape(lang, quote=True)}"' if lang else ""
                out.append(f"<pre><code{cls}>")
                in_code = True
            i += 1
            continue

        if in_code:
            out.append(html.escape(line))
            i += 1
            continue

        if not stripped:
            close_para()
            close_lists()
            close_table()
            i += 1
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            close_para()
            close_lists()
            close_table()
            level = len(m.group(1))
            out.append(f"<h{level}>{inline(m.group(2))}</h{level}>")
            i += 1
            continue

        if stripped.startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|?[\s:|-]+\|[\s:|-]*$", lines[i + 1]):
            close_para()
            close_lists()
            close_table()
            out.append("<table><thead>")
            out.append(table_row(stripped, header=True))
            out.append("</thead><tbody>")
            in_table = True
            i += 2
            continue

        if in_table and stripped.startswith("|"):
            out.append(table_row(stripped))
            i += 1
            continue
        if in_table:
            close_table()

        m = re.match(r"^[-*]\s+(.*)$", stripped)
        if m:
            close_para()
            if in_ol:
                out.append("</ol>")
                in_ol = False
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{inline(m.group(1))}</li>")
            i += 1
            continue

        m = re.match(r"^\d+\.\s+(.*)$", stripped)
        if m:
            close_para()
            if in_ul:
                out.append("</ul>")
                in_ul = False
            if not in_ol:
                out.append("<ol>")
                in_ol = True
            out.append(f"<li>{inline(m.group(1))}</li>")
            i += 1
            continue

        close_lists()
        para.append(stripped)
        i += 1

    close_para()
    close_lists()
    close_table()
    if in_code:
        out.append("</code></pre>")
    return "\n".join(out)


def document(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root {{ color-scheme: light dark; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.55; max-width: 1180px; margin: 32px auto; padding: 0 20px; }}
h1, h2, h3 {{ line-height: 1.2; }}
code {{ background: rgba(127, 127, 127, 0.16); padding: 0.12em 0.28em; border-radius: 4px; }}
pre {{ overflow-x: auto; padding: 14px; background: rgba(127, 127, 127, 0.14); border-radius: 6px; }}
pre code {{ background: transparent; padding: 0; }}
table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: 0.94rem; }}
th, td {{ border: 1px solid rgba(127, 127, 127, 0.35); padding: 6px 8px; text-align: left; vertical-align: top; }}
th {{ background: rgba(127, 127, 127, 0.14); }}
a {{ color: #0b66c3; }}
@media (prefers-color-scheme: dark) {{ a {{ color: #8ab4f8; }} }}
</style>
</head>
<body>
{body}
</body>
</html>
"""


def render_file(path: Path, out: Path | None = None) -> Path:
    text = path.read_text(errors="replace")
    title = next((line.lstrip("# ").strip() for line in text.splitlines() if line.startswith("#")), path.stem)
    html_path = out or path.with_suffix(".html")
    html_path.write_text(document(title, render_markdown(text)))
    return html_path


def main() -> None:
    args = parse_args()
    paths = [Path(p) for p in args.markdown]
    if args.out and len(paths) != 1:
        raise SystemExit("--out is only valid with one input file")
    for path in paths:
        print(render_file(path, Path(args.out) if args.out else None))


if __name__ == "__main__":
    main()
