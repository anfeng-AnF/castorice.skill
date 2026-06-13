from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from story_parser.coverage import (
        verify_story_markdown,
        write_json_report,
        write_markdown_report,
    )
    from story_parser.fetcher import read_text
    from story_parser.story_markdown import parse_story_markdown
else:
    from .story_parser.coverage import (
        verify_story_markdown,
        write_json_report,
        write_markdown_report,
    )
    from .story_parser.fetcher import read_text
    from .story_parser.story_markdown import parse_story_markdown


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "sources" / "static_pages" / "manifest.json"
DEFAULT_OUTPUT_DIR = ROOT / "sources" / "extracted"


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch parse mirrored BWiki story HTML pages and verify Markdown coverage."
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help=f"Mirror manifest. Default: {DEFAULT_MANIFEST}")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help=f"Output directory. Default: {DEFAULT_OUTPUT_DIR}")
    parser.add_argument("--limit", type=int, default=0, help="Maximum pages to process. 0 means no limit.")
    parser.add_argument("--max-items", type=int, default=80, help="Maximum missing/extra examples per coverage report.")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    pages = collect_pages(args.manifest, args.limit)
    if not pages:
        print("No pages with local_path found in manifest.", file=sys.stderr)
        return 2

    story_dir = args.output_dir / "story_pages"
    coverage_dir = args.output_dir / "coverage"
    story_dir.mkdir(parents=True, exist_ok=True)
    coverage_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for index, page in enumerate(pages, 1):
        html_path = page["html_path"]
        stem = output_stem(index, page)
        md_path = story_dir / f"{stem}.md"
        coverage_md_path = coverage_dir / f"{stem}.coverage.md"
        coverage_json_path = coverage_dir / f"{stem}.coverage.json"

        print(f"[{index}/{len(pages)}] {page['title']} ({page['version']})", file=sys.stderr)
        try:
            raw_html = read_text(html_path)
            rendered = parse_story_markdown(raw_html, display_path(html_path))
            md_path.write_text(rendered.markdown, encoding="utf-8", newline="\n")

            report = verify_story_markdown(html_path, md_path, max_items=args.max_items)
            write_markdown_report(coverage_md_path, report)
            write_json_report(coverage_json_path, report)

            row = {
                "index": index,
                "title": page["title"],
                "version": page["version"],
                "status": report.status,
                "html": display_path(html_path),
                "markdown": display_path(md_path),
                "coverage": display_path(coverage_md_path),
                **report.counts,
            }
        except Exception as exc:  # Keep batch runs useful even when one page is malformed.
            row = {
                "index": index,
                "title": page["title"],
                "version": page["version"],
                "status": "error",
                "html": display_path(html_path),
                "markdown": display_path(md_path),
                "coverage": display_path(coverage_md_path),
                "error": f"{type(exc).__name__}: {exc}",
            }
        rows.append(row)

    write_summary(args.output_dir / "coverage_summary.md", rows)
    (args.output_dir / "coverage_summary.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Wrote {args.output_dir / 'coverage_summary.md'}", file=sys.stderr)
    print(f"Wrote {args.output_dir / 'coverage_summary.json'}", file=sys.stderr)

    return 0 if not any(row["status"] in {"fail", "error"} for row in rows) else 1


def collect_pages(manifest_path: Path, limit: int) -> list[dict[str, Any]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    output_dir = manifest_output_dir(manifest, manifest_path)
    pages: list[dict[str, Any]] = []
    for page in manifest.get("pages", []):
        local_path = page.get("local_path")
        if not local_path:
            continue
        html_path = output_dir / local_path
        if not html_path.exists():
            continue
        pages.append(
            {
                "title": page.get("title") or Path(local_path).stem,
                "version": page.get("version") or "",
                "local_path": local_path,
                "html_path": html_path,
            }
        )
        if limit and len(pages) >= limit:
            break
    return pages


def output_stem(index: int, page: dict[str, Any]) -> str:
    title = sanitize_filename(page["title"])
    version = sanitize_filename(str(page["version"] or "unknown"))
    return f"{index:03d}_{version}_{title}"


def manifest_output_dir(manifest: dict[str, Any], manifest_path: Path) -> Path:
    value = manifest.get("output_dir")
    if not value:
        return manifest_path.parent
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def sanitize_filename(value: str) -> str:
    value = value.strip() or "page"
    value = "".join(char if char.isalnum() or char in "-_." else "_" for char in value)
    value = re.sub(r"_+", "_", value).strip("._")
    return value[:100] or "page"


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def write_summary(path: Path, rows: list[dict[str, Any]]) -> None:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1

    lines = [
        "# 剧情 Markdown 批量覆盖率汇总",
        "",
        "## 总览",
        "",
        f"- 页面数：{len(rows)}",
    ]
    for status in sorted(counts):
        lines.append(f"- `{status}`：{counts[status]}")

    lines.extend(
        [
            "",
            "## 页面明细",
            "",
            "| # | 版本 | 状态 | 标题 | 缺失 | 额外 | 选项异常 | 覆盖率报告 |",
            "| ---: | --- | --- | --- | ---: | ---: | ---: | --- |",
        ]
    )
    for row in rows:
        coverage_link = relative_link(Path(row["coverage"]), path.parent)
        lines.append(
            "| {index} | {version} | `{status}` | {title} | {missing} | {extra} | {plot} | [{coverage}]({coverage}) |".format(
                index=row["index"],
                version=row.get("version") or "",
                status=row["status"],
                title=escape_table_text(row["title"]),
                missing=row.get("missing_groups", "-"),
                extra=row.get("extra_groups", "-"),
                plot=row.get("plot_mismatches", "-"),
                coverage=coverage_link,
            )
        )

    problem_rows = [row for row in rows if row["status"] != "pass"]
    lines.extend(["", "## 异常页", ""])
    if not problem_rows:
        lines.append("- 未发现异常页。")
    else:
        for row in problem_rows:
            detail = row.get("error") or (
                f"missing={row.get('missing_groups')}, "
                f"extra={row.get('extra_groups')}, "
                f"plot_mismatches={row.get('plot_mismatches')}"
            )
            lines.append(f"- `{row['status']}` {row['index']:03d} {row['title']}：{detail}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def escape_table_text(value: str) -> str:
    return value.replace("|", "\\|")


def relative_link(target: Path, base_dir: Path) -> str:
    target_path = target if target.is_absolute() else ROOT / target
    try:
        return target_path.resolve().relative_to(base_dir.resolve()).as_posix()
    except ValueError:
        return target.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
