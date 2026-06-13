from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Optional, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from story_parser.adapters import extract_bwiki_page_info
    from story_parser.fetcher import read_text
    from story_parser.html_tree import HtmlNode, find_first, parse_html, text_content
    from story_parser.story_markdown import (
        StoryMarkdownRenderer,
        headline_text,
        repair_standalone_dialogue_lines,
        tidy_markdown,
    )
else:
    from .story_parser.adapters import extract_bwiki_page_info
    from .story_parser.fetcher import read_text
    from .story_parser.html_tree import HtmlNode, find_first, parse_html, text_content
    from .story_parser.story_markdown import (
        StoryMarkdownRenderer,
        headline_text,
        repair_standalone_dialogue_lines,
        tidy_markdown,
    )


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HTML = ROOT / "sources" / "static_pages" / "067_资料.html"
DEFAULT_OUTPUT = ROOT / "sources" / "extracted" / "profile_pages" / "067_资料_大世界对话.md"


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract the 大世界对话 section from a BWiki character profile page."
    )
    parser.add_argument("--html", type=Path, default=DEFAULT_HTML, help=f"Local HTML file. Default: {DEFAULT_HTML}")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help=f"Markdown output. Default: {DEFAULT_OUTPUT}")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    raw_html = read_text(args.html)
    result = parse_profile_world_dialogue(raw_html, display_path(args.html))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result, encoding="utf-8", newline="\n")
    print(f"Wrote {display_path(args.output)}", file=sys.stderr)
    return 0


def parse_profile_world_dialogue(raw_html: str, source: str) -> str:
    info = extract_bwiki_page_info(raw_html, source)
    root = parse_html(raw_html)
    parser_root = find_first(root, lambda node: node.has_class("mw-parser-output")) or root
    nodes = collect_world_dialogue_nodes(parser_root)

    renderer = StoryMarkdownRenderer()
    renderer.lines = [
        f"# {info.title or '角色资料'} - 大世界对话",
        "",
        "> Generated from local/static BWiki HTML. Review branch choices before using as evidence.",
        "",
        f"- Source: {source}",
        f"- Version: {info.version or '(unknown)'}",
        "",
        "## 角色对话",
        "",
        "### 大世界对话",
        "",
    ]
    renderer.dialogue_count = 0
    renderer.choice_group_count = 0

    for node in nodes:
        renderer.render_node(node)

    markdown = tidy_markdown(repair_standalone_dialogue_lines(renderer.lines))
    markdown = renumber_choice_groups(markdown)
    dialogue_count = count_dialogue_lines(markdown)
    choice_group_count = count_choice_groups(markdown)
    stats = (
        "<!-- parser_stats: "
        f"title={info.title}; version={info.version or '(unknown)'}; "
        f"dialogue_count={dialogue_count}; "
        f"choice_group_count={choice_group_count} -->"
    )
    return markdown.rstrip() + "\n\n" + stats + "\n"


def collect_world_dialogue_nodes(root: HtmlNode) -> list[HtmlNode]:
    children = root.element_children()
    start_index: int | None = None
    for index, child in enumerate(children):
        if child.tag == "h3" and normalize_heading(child) == "大世界对话":
            start_index = index + 1
            break

    if start_index is None:
        raise ValueError("Cannot find heading: 大世界对话")

    selected: list[HtmlNode] = []
    for child in children[start_index:]:
        if child.tag == "h2":
            break
        selected.append(child)
    return selected


def normalize_heading(node: HtmlNode) -> str:
    return (headline_text(node) or text_content(node)).strip()


def renumber_choice_groups(markdown: str) -> str:
    counter = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal counter
        counter += 1
        return f"{match.group(1)}> 选项组 {counter}："

    return re.sub(r"(?m)^(\s*)> 选项组 \d+：", replace, markdown)


def count_dialogue_lines(markdown: str) -> int:
    return len(re.findall(r"(?m)^\s*- \*\*[^*]+\*\*：", markdown))


def count_choice_groups(markdown: str) -> int:
    return len(re.findall(r"(?m)^\s*> 选项组 \d+：", markdown))


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
