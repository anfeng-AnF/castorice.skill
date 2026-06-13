from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any, Optional, Sequence

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from story_parser.adapters import StoryLink, extract_bwiki_page_info
    from story_parser.fetcher import SourceFetcher, load_url_file, safe_cache_name
else:
    from .adapters import StoryLink, extract_bwiki_page_info
    from .fetcher import SourceFetcher, load_url_file, safe_cache_name


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "sources" / "static_pages"


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mirror one or more BWiki story HTML pages locally."
    )
    parser.add_argument("--url", action="append", default=[], help="Entry/detail URL. Repeatable.")
    parser.add_argument("--urls-file", type=Path, help="File containing one URL per line.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help=f"Static HTML output directory. Default: {DEFAULT_OUTPUT_DIR}")
    parser.add_argument("--single-step", action="store_true", help="Download only the given page(s), print relation candidates, and do not follow them.")
    parser.add_argument("--follow-links", action="store_true", help="Auto-follow discovered task relation links. Ignored in --single-step mode.")
    parser.add_argument("--follow-detail-links", action="store_true", help="Compatibility alias for --follow-links.")
    parser.add_argument("--follow-types", default="next_task", help="Comma-separated relation types to auto-follow. Default: next_task.")
    parser.add_argument("--min-version", default=None, help="Inclusive minimum story version, e.g. 3.0.")
    parser.add_argument("--max-version", default=None, help="Exclusive maximum story version, e.g. 4.0.")
    parser.add_argument("--max-pages", type=int, default=0, help="Maximum accepted pages to mirror in this run. 0 means no limit.")
    parser.add_argument("--delay", type=float, default=2.0, help="Seconds to sleep between network requests.")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds.")
    parser.add_argument("--retries", type=int, default=3, help="HTTP retry count.")
    parser.add_argument("--retry-sleep", type=float, default=2.0, help="Seconds between retries.")
    parser.add_argument("--force", action="store_true", help="Re-download pages even when local HTML exists.")
    parser.add_argument("--dry-run", action="store_true", help="Print initial URL plan without downloading.")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    urls = dedupe(collect_urls(args))
    if not urls:
        print("No input. Use --url or --urls-file.", file=sys.stderr)
        return 2

    if args.dry_run:
        for url in urls:
            print(url)
        return 0

    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output_dir / "manifest.json"
    graph_path = args.output_dir / "task_graph.json"
    manifest = load_manifest(manifest_path, args.output_dir)
    graph = load_graph(graph_path)
    recovered = sync_manifest_from_local_html(
        args.output_dir,
        manifest,
        graph,
        args.min_version,
        args.max_version,
    )
    if recovered:
        save_state(manifest_path, graph_path, manifest, graph, args)
        print(f"[recovered] {recovered} local HTML page(s)", file=sys.stderr)

    fetcher = SourceFetcher(
        cache_dir=None,
        timeout=args.timeout,
        retries=args.retries,
        retry_sleep=args.retry_sleep,
    )
    follow_types = parse_follow_types(args.follow_types)

    queue = list(urls)
    seen_this_run: set[str] = set()
    accepted_this_run = 0
    processed_this_run = 0

    while queue:
        if args.single_step and processed_this_run >= len(urls):
            break
        if args.max_pages and accepted_this_run >= args.max_pages:
            break

        url = normalize_url(queue.pop(0))
        if url in seen_this_run:
            continue
        seen_this_run.add(url)

        existing_page = find_manifest_page(manifest, url)
        existing_path = page_local_path(args.output_dir, existing_page)

        if existing_path and existing_path.exists() and not args.force:
            print(f"[cached] {url}", file=sys.stderr)
            raw_html = existing_path.read_text(encoding="utf-8", errors="replace")
            fetch_status = "cached"
            local_path = existing_path
        else:
            if processed_this_run:
                time.sleep(args.delay)
            print(f"[fetch] {url}", file=sys.stderr)
            raw_html = fetcher.fetch_url(url)
            fetch_status = "fetched"
            local_path = None

        info = extract_bwiki_page_info(raw_html, url)
        version_status = classify_version(info.version, args.min_version, args.max_version)
        should_store = version_status in {"in_range", "version_unknown"}

        if should_store and local_path is None:
            local_path = args.output_dir / make_page_filename(url, next_page_index(manifest))
            local_path.write_text(raw_html, encoding="utf-8", newline="\n")
        elif not should_store:
            fetch_status = "skipped_by_version"

        rel_path = str(local_path.relative_to(args.output_dir)).replace("\\", "/") if local_path else None
        discovered_links = [link_to_dict(link) for link in info.links]

        upsert_manifest_page(
            manifest,
            {
                "url": url,
                "title": info.title,
                "version": info.version,
                "local_path": rel_path,
                "status": fetch_status,
                "version_status": version_status,
                "discovered_links": discovered_links,
            },
        )
        upsert_graph_node(graph, url, info.title, info.version, rel_path, version_status)
        for link in info.links:
            add_graph_edge(graph, url, link)

        save_state(manifest_path, graph_path, manifest, graph, args)
        print_step_summary(info.title, info.version, rel_path, version_status, info.links)

        processed_this_run += 1
        if should_store:
            accepted_this_run += 1

        if not args.single_step and (args.follow_links or args.follow_detail_links) and version_status == "in_range":
            for link in info.links:
                if link.link_type in follow_types and link.url not in seen_this_run and not find_manifest_page(manifest, link.url):
                    queue.append(link.url)

    save_state(manifest_path, graph_path, manifest, graph, args)
    print(f"Wrote {manifest_path}", file=sys.stderr)
    print(f"Wrote {graph_path}", file=sys.stderr)
    return 0


def collect_urls(args: argparse.Namespace) -> list[str]:
    urls = list(args.url)
    if args.urls_file:
        urls.extend(load_url_file(args.urls_file))
    return urls


def load_manifest(path: Path, output_dir: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "generated_at": None,
        "output_dir": str(output_dir),
        "single_step": False,
        "follow_links": False,
        "page_count": 0,
        "pages": [],
    }


def load_graph(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"generated_at": None, "nodes": [], "edges": []}


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def save_state(
    manifest_path: Path,
    graph_path: Path,
    manifest: dict[str, Any],
    graph: dict[str, Any],
    args: argparse.Namespace,
) -> None:
    manifest["generated_at"] = now_iso()
    manifest["output_dir"] = display_path(args.output_dir)
    manifest["single_step"] = bool(args.single_step)
    manifest["follow_links"] = bool(args.follow_links or args.follow_detail_links)
    manifest["follow_types"] = args.follow_types
    manifest["min_version"] = args.min_version
    manifest["max_version"] = args.max_version
    manifest["page_count"] = len(manifest.get("pages", []))
    graph["generated_at"] = manifest["generated_at"]
    write_json(manifest_path, manifest)
    write_json(graph_path, graph)


def sync_manifest_from_local_html(
    output_dir: Path,
    manifest: dict[str, Any],
    graph: dict[str, Any],
    min_version: str | None,
    max_version: str | None,
) -> int:
    recovered = 0
    known_local_paths = {
        (page.get("local_path") or "").replace("\\", "/")
        for page in manifest.get("pages", [])
        if page.get("local_path")
    }

    for html_path in sorted(output_dir.glob("*.html")):
        rel_path = str(html_path.relative_to(output_dir)).replace("\\", "/")
        if rel_path in known_local_paths:
            continue

        raw_html = html_path.read_text(encoding="utf-8", errors="replace")
        source_url = extract_html_source_url(raw_html)
        if not source_url:
            continue

        info = extract_bwiki_page_info(raw_html, source_url)
        version_status = classify_version(info.version, min_version, max_version)
        discovered_links = [link_to_dict(link) for link in info.links]
        upsert_manifest_page(
            manifest,
            {
                "url": normalize_url(source_url),
                "title": info.title,
                "version": info.version,
                "local_path": rel_path,
                "status": "recovered",
                "version_status": version_status,
                "discovered_links": discovered_links,
            },
        )
        upsert_graph_node(graph, source_url, info.title, info.version, rel_path, version_status)
        for link in info.links:
            add_graph_edge(graph, source_url, link)
        recovered += 1

    return recovered


def extract_html_source_url(raw_html: str) -> str | None:
    for pattern in (
        r'<meta\s+property=["\']og:url["\']\s+content=["\']([^"\']+)["\']',
        r'<link\s+rel=["\']canonical["\']\s+href=["\']([^"\']+)["\']',
    ):
        match = re.search(pattern, raw_html, re.IGNORECASE)
        if match:
            return normalize_url(html.unescape(match.group(1)))

    match = re.search(r'"wgPageName"\s*:\s*"([^"]+)"', raw_html)
    if not match:
        return None
    page_name = html.unescape(match.group(1))
    quoted = urllib.parse.quote(page_name, safe="")
    return f"https://wiki.biligame.com/sr/{quoted}"


def normalize_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", parsed.query, ""))


def find_manifest_page(manifest: dict[str, Any], url: str) -> dict[str, Any] | None:
    url = normalize_url(url)
    for page in manifest.get("pages", []):
        if normalize_url(page.get("url", "")) == url:
            return page
    return None


def page_local_path(output_dir: Path, page: dict[str, Any] | None) -> Path | None:
    if not page or not page.get("local_path"):
        return None
    return output_dir / page["local_path"]


def upsert_manifest_page(manifest: dict[str, Any], page: dict[str, Any]) -> None:
    existing = find_manifest_page(manifest, page["url"])
    if existing is not None:
        existing.update(page)
        return
    manifest.setdefault("pages", []).append(page)


def upsert_graph_node(
    graph: dict[str, Any],
    url: str,
    title: str,
    version: str | None,
    local_path: str | None,
    version_status: str,
) -> None:
    url = normalize_url(url)
    nodes = graph.setdefault("nodes", [])
    for node in nodes:
        if normalize_url(node.get("url", "")) == url:
            node.update(
                {
                    "title": title,
                    "version": version,
                    "local_path": local_path,
                    "version_status": version_status,
                }
            )
            return
    nodes.append(
        {
            "url": url,
            "title": title,
            "version": version,
            "local_path": local_path,
            "version_status": version_status,
        }
    )


def add_graph_edge(graph: dict[str, Any], source_url: str, link: StoryLink) -> None:
    edge = {
        "from": normalize_url(source_url),
        "to": normalize_url(link.url),
        "type": link.link_type,
        "label": link.label,
        "title": link.title,
    }
    edges = graph.setdefault("edges", [])
    for existing in edges:
        if (
            existing.get("from") == edge["from"]
            and existing.get("to") == edge["to"]
            and existing.get("type") == edge["type"]
        ):
            existing.update(edge)
            return
    edges.append(edge)


def link_to_dict(link: StoryLink) -> dict[str, str]:
    return {
        "url": normalize_url(link.url),
        "title": link.title,
        "type": link.link_type,
        "label": link.label,
    }


def classify_version(version: str | None, min_version: str | None, max_version: str | None) -> str:
    if not version:
        return "version_unknown"

    value = parse_version(version)
    if value is None:
        return "version_unknown"

    min_value = parse_version(min_version) if min_version else None
    max_value = parse_version(max_version) if max_version else None

    if min_value is not None and compare_versions(value, min_value) < 0:
        return "skipped_by_min_version"
    if max_value is not None and compare_versions(value, max_value) >= 0:
        return "skipped_by_max_version"
    return "in_range"


def parse_version(value: str | None) -> tuple[int, ...] | None:
    if not value:
        return None
    match = re.search(r"\d+(?:\.\d+)*", value)
    if not match:
        return None
    return tuple(int(part) for part in match.group(0).split("."))


def compare_versions(left: tuple[int, ...], right: tuple[int, ...]) -> int:
    size = max(len(left), len(right))
    lpad = left + (0,) * (size - len(left))
    rpad = right + (0,) * (size - len(right))
    return (lpad > rpad) - (lpad < rpad)


def make_page_filename(url: str, index: int) -> str:
    parsed = urllib.parse.urlparse(url)
    leaf = urllib.parse.unquote(Path(parsed.path).name)
    if not leaf:
        leaf = safe_cache_name(url).removesuffix(".html")
    leaf = sanitize_filename(leaf)
    return f"{index:03d}_{leaf}.html"


def sanitize_filename(value: str) -> str:
    value = value.strip() or "page"
    value = "".join(char if char.isalnum() or char in "-_." else "_" for char in value)
    value = value.strip("._")
    return value[:120] or "page"


def next_page_index(manifest: dict[str, Any]) -> int:
    max_index = 0
    for page in manifest.get("pages", []):
        local_path = page.get("local_path") or ""
        match = re.match(r"(\d+)_", Path(local_path).name)
        if match:
            max_index = max(max_index, int(match.group(1)))
    return max_index + 1


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = normalize_url(value)
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def parse_follow_types(value: str) -> set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


def print_step_summary(
    title: str,
    version: str | None,
    local_path: str | None,
    version_status: str,
    links: list[StoryLink],
) -> None:
    print(f"Downloaded: {title or '(unknown title)'}")
    print(f"Version: {version or '(unknown)'} [{version_status}]")
    print(f"Local: {local_path or '(not stored)'}")
    print("")
    print("Relation candidates:")
    if not links:
        print("(none)")
        return
    for index, link in enumerate(links, 1):
        print(f"{index}. [{link.link_type}] {link.title} -> {normalize_url(link.url)}")


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
