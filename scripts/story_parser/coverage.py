from __future__ import annotations

import html
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, Sequence

from .fetcher import read_text
from .html_tree import HtmlNode, find_first, parse_html, text_content
from .normalize import parse_speaker
from .story_markdown import (
    collect_story_content_nodes,
    extract_message_lines,
    has_block_children,
    headline_text,
    plot_frame_children,
)


ROOT = Path(__file__).resolve().parents[2]


@dataclass
class SourceItem:
    kind: str
    text: str
    path: str


@dataclass
class PlotFrameStat:
    index: int
    path: str
    options: int
    contents: int


@dataclass
class MissingItem:
    kind: str
    text: str
    path: str
    expected_count: int
    observed_count: int


@dataclass
class ExtraItem:
    kind: str
    text: str
    observed_count: int
    source_count: int


@dataclass
class CoverageReport:
    html_path: str
    markdown_path: str
    status: str
    counts: dict[str, int]
    plot_mismatches: list[PlotFrameStat]
    missing_items: list[MissingItem]
    extra_items: list[ExtraItem]


class SourceInventoryBuilder:
    def __init__(self) -> None:
        self.items: list[SourceItem] = []
        self.plot_frames: list[PlotFrameStat] = []
        self.plot_index = 0
        self.message_count = 0

    def collect(self, raw_html: str) -> None:
        root = parse_html(raw_html)
        parser_root = find_first(root, lambda node: node.has_class("mw-parser-output")) or root
        for node in collect_story_content_nodes(parser_root):
            self.collect_node(node, ["剧情内容"])

    def collect_node(self, node: HtmlNode, context: list[str]) -> None:
        if should_skip_node(node):
            return

        if node.tag in {"h2", "h3", "h4", "h5", "h6"}:
            title = headline_text(node) or text_content(node)
            if title:
                self.add("heading", title, context)
            return

        if node.has_class("sr-collapse-frame"):
            title_node = find_first(node, lambda child: child.has_class("sr-collapse-title"))
            content_node = find_first(node, lambda child: child.has_class("sr-collapse-content"))
            title = text_content(title_node) if title_node else "折叠内容"
            self.add("collapse_title", title, context)
            if content_node:
                self.collect_children(content_node.children, context + [title])
            return

        if node.has_class("plotFrame"):
            self.collect_plot_frame(node, context)
            return

        if node.has_class("messageContent"):
            messages = extract_message_lines(node)
            for speaker, message in messages:
                self.message_count += 1
                self.add("message_dialogue", f"{speaker}：{message}", context)
            return

        if node.tag in {"ul", "ol"}:
            self.collect_children(node.element_children(), context)
            return

        if node.tag == "li":
            if has_block_children(node):
                self.collect_children(node.children, context)
            else:
                self.add_text_item(text_content(node), context)
            return

        if has_block_children(node):
            self.collect_children(node.children, context)
            return

        self.add_text_item(text_content(node), context)

    def collect_children(self, nodes: Sequence[HtmlNode], context: list[str]) -> None:
        for child in nodes:
            if child.tag == "#text":
                self.add_text_item(child.text, context)
                continue
            self.collect_node(child, context)

    def collect_plot_frame(self, node: HtmlNode, context: list[str]) -> None:
        self.plot_index += 1
        frame_label = f"plotFrame[{self.plot_index}]"
        children = plot_frame_children(node)
        options = [child for child in children if child.has_class("plotOptions")]
        contents = [child for child in children if child.has_class("content")]
        frame_path = " / ".join(context + [frame_label])
        self.plot_frames.append(
            PlotFrameStat(
                index=self.plot_index,
                path=frame_path,
                options=len(options),
                contents=len(contents),
            )
        )

        for index, option in enumerate(options, 1):
            self.add("plot_option", text_content(option), context + [frame_label, f"option[{index}]"])

        for index, content in enumerate(contents, 1):
            self.collect_children(content.children, context + [frame_label, f"content[{index}]"])

    def add_text_item(self, text: str, context: list[str]) -> None:
        if not text:
            return
        kind = "dialogue" if parse_speaker(text) else "text"
        self.add(kind, text, context)

    def add(self, kind: str, text: str, context: list[str]) -> None:
        text = clean_text(text)
        if not text or text in {">", "›"}:
            return
        self.items.append(SourceItem(kind=kind, text=text, path=" / ".join(context)))


def verify_story_markdown(
    html_path: Path,
    markdown_path: Path,
    max_items: int = 80,
) -> CoverageReport:
    raw_html = read_text(html_path)
    markdown = read_text(markdown_path)

    builder = SourceInventoryBuilder()
    builder.collect(raw_html)

    source_groups = group_source_items(builder.items)
    markdown_text = normalize_text_for_match(markdown_to_plain_text(markdown))
    missing = find_missing_items(source_groups, markdown_text, max_items)

    source_text = normalize_text_for_match("\n".join(item.text for item in builder.items))
    markdown_items = extract_markdown_items(markdown)
    extra = find_extra_items(markdown_items, source_text, max_items)

    plot_mismatches = [
        frame for frame in builder.plot_frames if frame.options != frame.contents
    ]
    counts = {
        "source_items": len(builder.items),
        "source_dialogue_items": count_kinds(builder.items, {"dialogue", "message_dialogue"}),
        "source_message_dialogue": builder.message_count,
        "source_plot_frames": len(builder.plot_frames),
        "source_plot_options": sum(frame.options for frame in builder.plot_frames),
        "source_plot_contents": sum(frame.contents for frame in builder.plot_frames),
        "markdown_dialogue_lines": count_markdown_dialogue_lines(markdown),
        "markdown_choice_groups": count_markdown_choice_groups(markdown),
        "markdown_option_lines": count_markdown_option_lines(markdown),
        "missing_groups": len(missing),
        "extra_groups": len(extra),
        "plot_mismatches": len(plot_mismatches),
    }

    status = "pass"
    if missing:
        status = "fail"
    elif plot_mismatches or extra:
        status = "warn"

    return CoverageReport(
        html_path=display_path(html_path),
        markdown_path=display_path(markdown_path),
        status=status,
        counts=counts,
        plot_mismatches=plot_mismatches[:max_items],
        missing_items=missing,
        extra_items=extra,
    )


def write_markdown_report(path: Path, report: CoverageReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 剧情 Markdown 覆盖率报告",
        "",
        f"- HTML: `{report.html_path}`",
        f"- Markdown: `{report.markdown_path}`",
        f"- 状态: `{report.status}`",
        "",
        "## 计数",
        "",
        "| 项目 | 数量 |",
        "| --- | ---: |",
    ]
    for key, value in report.counts.items():
        lines.append(f"| `{key}` | {value} |")

    lines.extend(["", "## 选项结构异常", ""])
    if report.plot_mismatches:
        for frame in report.plot_mismatches:
            lines.append(
                f"- `{frame.path}`: options={frame.options}, contents={frame.contents}"
            )
    else:
        lines.append("- 未发现 `plotOptions` 与 `content` 数量不一致的选项组。")

    lines.extend(["", "## HTML 中有但 Markdown 中疑似缺失", ""])
    if report.missing_items:
        for item in report.missing_items:
            lines.append(
                f"- `{item.kind}` `{item.path}` "
                f"expected={item.expected_count}, observed={item.observed_count}: {item.text}"
            )
    else:
        lines.append("- 未发现缺失文本组。")

    lines.extend(["", "## Markdown 中有但 HTML 源清单中未匹配", ""])
    if report.extra_items:
        for item in report.extra_items:
            lines.append(
                f"- `{item.kind}` observed={item.observed_count}, "
                f"source={item.source_count}: {item.text}"
            )
    else:
        lines.append("- 未发现额外文本组。")

    lines.extend(
        [
            "",
            "## 说明",
            "",
            "- 该报告使用空白无关匹配，因此换行、缩进、Markdown 标记不会造成误报。",
            "- `source_plot_frames` 是 HTML 中所有选项组数量，包含嵌套分支。",
            "- 缺失项为强信号；额外项可能来自解析器添加的结构化说明，需要人工判断。",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def write_json_report(path: Path, report: CoverageReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(report), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def group_source_items(items: Iterable[SourceItem]) -> dict[str, list[SourceItem]]:
    grouped: dict[str, list[SourceItem]] = defaultdict(list)
    for item in items:
        key = normalize_text_for_match(item.text)
        if key:
            grouped[key].append(item)
    return grouped


def find_missing_items(
    source_groups: dict[str, list[SourceItem]],
    markdown_text: str,
    max_items: int,
) -> list[MissingItem]:
    missing: list[MissingItem] = []
    for key, items in source_groups.items():
        observed = markdown_text.count(key)
        expected = len(items)
        if observed >= expected:
            continue
        for item in items[observed:expected]:
            missing.append(
                MissingItem(
                    kind=item.kind,
                    text=item.text,
                    path=item.path,
                    expected_count=expected,
                    observed_count=observed,
                )
            )
            if len(missing) >= max_items:
                return missing
    return missing


def find_extra_items(
    markdown_items: list[tuple[str, str]],
    source_text: str,
    max_items: int,
) -> list[ExtraItem]:
    counter = Counter(
        (kind, normalize_text_for_match(text), clean_text(text))
        for kind, text in markdown_items
        if normalize_text_for_match(text)
    )
    extra: list[ExtraItem] = []
    for (kind, key, display_text), observed in counter.items():
        source_count = source_text.count(key)
        if source_count >= observed:
            continue
        extra.append(
            ExtraItem(
                kind=kind,
                text=display_text,
                observed_count=observed,
                source_count=source_count,
            )
        )
        if len(extra) >= max_items:
            break
    return extra


def extract_markdown_items(markdown: str) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if should_skip_markdown_line(line):
            continue

        dialogue = re.match(r"^-\s+\*\*([^*]+)\*\*[：:]\s*(.+)$", line)
        if dialogue:
            items.append(("markdown_dialogue_text", dialogue.group(2)))
            continue

        option = re.match(r"^-\s+选项\s+\d+（[^）]*）：(.+)$", line)
        if option:
            items.append(("markdown_option", option.group(1)))
            continue

        heading = re.match(r"^(#{2,6})\s+(.+)$", line)
        if heading:
            items.append(("markdown_heading", heading.group(2)))
            continue

        bullet = re.match(r"^-\s+(.+)$", line)
        if bullet:
            items.append(("markdown_text", bullet.group(1)))
            continue

        line = re.sub(r"^\s*>\s+", "", line)
        if line:
            items.append(("markdown_text", line))
    return items


def markdown_to_plain_text(markdown: str) -> str:
    text = re.sub(r"<!--.*?-->", "", markdown, flags=re.DOTALL)
    text = re.sub(r"\*\*([^*]+)\*\*[：:]", r"\1：", text)
    text = re.sub(r"^\s*[-*]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*>\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return text


def should_skip_markdown_line(line: str) -> bool:
    if not line:
        return True
    if line in {">", "›"}:
        return True
    if line.startswith("<!--"):
        return True
    if line.startswith("# "):
        return True
    if line.startswith("> Generated"):
        return True
    if line.startswith("> 选项组"):
        return True
    if line in {"# Story Markdown Preview", "## 剧情内容", "- 回复：", "回复："}:
        return True
    if line.startswith("- Source:") or line.startswith("- Version:"):
        return True
    if line.endswith("回复：无额外文本") or line == "- 回复：无额外文本":
        return True
    if "回复：未在 HTML 中找到对应 content 块" in line:
        return True
    return False


def clean_text(text: str) -> str:
    text = html.unescape(text)
    text = text.replace("\u00a0", " ").replace("\u3000", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n+", "\n", text)
    return text.strip()


def normalize_text_for_match(text: str) -> str:
    text = clean_text(text)
    text = re.sub(r"\s+", "", text)
    text = text.replace(":", "：")
    return text


def should_skip_node(node: HtmlNode) -> bool:
    if node.tag in {"script", "style", "noscript", "svg", "canvas", "iframe", "table"}:
        return True
    classes = node.classes()
    return bool(
        classes
        & {
            "toc",
            "mw-editsection",
            "resourceLoader",
            "printfooter",
            "catlinks",
            "navbox",
            "plotIcon",
        }
    )


def count_kinds(items: Iterable[SourceItem], kinds: set[str]) -> int:
    return sum(1 for item in items if item.kind in kinds)


def count_markdown_dialogue_lines(markdown: str) -> int:
    return len(re.findall(r"(?m)^-\s+\*\*[^*]+\*\*[：:]", markdown))


def count_markdown_choice_groups(markdown: str) -> int:
    return len(re.findall(r"(?m)^\s*>\s+选项组\s+\d+", markdown))


def count_markdown_option_lines(markdown: str) -> int:
    return len(re.findall(r"(?m)^\s*-\s+选项\s+\d+（", markdown))


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()
