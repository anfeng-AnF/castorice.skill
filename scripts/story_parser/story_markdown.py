from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .adapters import extract_bwiki_page_info
from .html_tree import HtmlNode, find_all, find_first, parse_html, text_content
from .normalize import DEFAULT_SPEAKER_HINTS, parse_speaker


BLOCK_TAGS = {"div", "ul", "ol", "li", "p", "table", "h2", "h3", "h4", "h5", "h6"}
SKIP_CLASSES = {
    "toc",
    "mw-editsection",
    "resourceLoader",
    "printfooter",
    "catlinks",
    "navbox",
}


@dataclass
class StoryMarkdownResult:
    title: str
    version: str | None
    source: str
    markdown: str
    dialogue_count: int
    choice_group_count: int


class StoryMarkdownRenderer:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.dialogue_count = 0
        self.choice_group_count = 0

    def render(self, raw_html: str, source: str) -> StoryMarkdownResult:
        info = extract_bwiki_page_info(raw_html, source)
        root = parse_html(raw_html)
        parser_root = find_first(root, lambda node: node.has_class("mw-parser-output")) or root
        story_nodes = collect_story_content_nodes(parser_root)

        self.lines = [
            f"# {info.title or Path(source).stem}",
            "",
            "> Generated from local/static BWiki HTML. Review branch choices before using as evidence.",
            "",
            f"- Source: {source}",
            f"- Version: {info.version or '(unknown)'}",
            "",
            "## 剧情内容",
            "",
        ]
        self.dialogue_count = 0
        self.choice_group_count = 0

        for node in story_nodes:
            self.render_node(node)

        return StoryMarkdownResult(
            title=info.title,
            version=info.version,
            source=source,
            markdown=tidy_markdown(repair_standalone_dialogue_lines(self.lines)),
            dialogue_count=self.dialogue_count,
            choice_group_count=self.choice_group_count,
        )

    def render_node(self, node: HtmlNode) -> None:
        if should_skip(node):
            return

        if node.tag in {"h2", "h3", "h4", "h5", "h6"}:
            self.render_heading(node)
            return

        if node.has_class("sr-collapse-frame"):
            self.render_collapse(node)
            return

        if node.has_class("plotFrame"):
            self.render_plot_frame(node)
            return

        if node.has_class("messageContent"):
            self.render_message_content(node)
            return

        if node.tag in {"ul", "ol"}:
            self.render_list(node)
            return

        if node.tag == "li" and has_block_children(node):
            self.render_children(node.children)
            return

        if node.tag == "li":
            self.render_list_item(node)
            return

        if has_block_children(node):
            self.render_children(node.children)
            return

        if node.tag == "p":
            self.render_paragraph(node)
            return

        self.render_paragraph(node)

    def render_children(self, nodes: Sequence[HtmlNode]) -> None:
        for child in nodes:
            if child.tag == "#text":
                self.render_paragraph(child)
                continue
            self.render_node(child)

    def render_heading(self, node: HtmlNode) -> None:
        title = headline_text(node) or text_content(node)
        if not title:
            return
        level = min(max(int(node.tag[1]), 2), 5)
        self.add_blank()
        self.lines.append(f"{'#' * level} {title}")
        self.add_blank()

    def render_collapse(self, node: HtmlNode) -> None:
        title_node = find_first(node, lambda child: child.has_class("sr-collapse-title"))
        content_node = find_first(node, lambda child: child.has_class("sr-collapse-content"))
        title = text_content(title_node) if title_node else "折叠内容"

        self.add_blank()
        self.lines.append(f"#### {title}")
        self.add_blank()
        if content_node:
            self.render_children(content_node.children)

    def render_plot_frame(self, node: HtmlNode) -> None:
        children = plot_frame_children(node)
        options = [child for child in children if child.has_class("plotOptions")]
        contents = [child for child in children if child.has_class("content")]
        if not options:
            self.render_children(node.children)
            return

        self.choice_group_count += 1
        self.add_blank()
        self.lines.append(f"> 选项组 {self.choice_group_count}：{len(options)} 个选项")
        self.add_blank()

        for index, option in enumerate(options, 1):
            label = option_label(option)
            text = text_content(option)
            active = "，默认显示" if option.has_class("plotActive") else ""
            self.lines.append(f"- 选项 {index}（{label}{active}）：{text or '(空选项)'}")

            if index - 1 >= len(contents):
                self.lines.append("  - 回复：未在 HTML 中找到对应 content 块")
                continue

            branch_lines = render_branch_lines(contents[index - 1])
            if not branch_lines:
                self.lines.append("  - 回复：无额外文本")
                continue
            self.lines.append("  - 回复：")
            for branch_line in branch_lines:
                self.lines.append(f"    {branch_line}")
                if branch_line.startswith("- **"):
                    self.dialogue_count += 1
        self.add_blank()

    def render_message_content(self, node: HtmlNode) -> None:
        messages = extract_message_lines(node)
        for speaker, text in messages:
            self.lines.append(format_dialogue(speaker, text))
            self.dialogue_count += 1

    def render_list(self, node: HtmlNode) -> None:
        for child in node.element_children():
            if child.tag == "li":
                self.render_list_item(child)

    def render_list_item(self, node: HtmlNode) -> None:
        text = text_content(node)
        if not text:
            return
        speaker = parse_speaker(text)
        if speaker:
            name, content = speaker
            self.lines.append(format_dialogue(name, content))
            self.dialogue_count += 1
        else:
            self.lines.append(f"- {text}")

    def render_paragraph(self, node: HtmlNode) -> None:
        text = text_content(node)
        if not text:
            return
        speaker = parse_speaker(text)
        if speaker:
            name, content = speaker
            self.lines.append(format_dialogue(name, content))
            self.dialogue_count += 1
            return
        self.lines.append(text)
        self.add_blank()

    def add_blank(self) -> None:
        if self.lines and self.lines[-1] != "":
            self.lines.append("")


def parse_story_markdown(raw_html: str, source: str) -> StoryMarkdownResult:
    return StoryMarkdownRenderer().render(raw_html, source)


def plot_frame_children(node: HtmlNode) -> list[HtmlNode]:
    boxes = [child for child in node.element_children() if child.has_class("plotBox")]
    if boxes:
        children: list[HtmlNode] = []
        for box in boxes:
            children.extend(box.element_children())
        return children
    return node.element_children()


def collect_story_content_nodes(root: HtmlNode) -> list[HtmlNode]:
    children = root.element_children()
    start_index = None
    for index, child in enumerate(children):
        if child.tag == "h2" and headline_text(child) == "剧情内容":
            start_index = index + 1
            break
    if start_index is None:
        return children
    return children[start_index:]


def should_skip(node: HtmlNode) -> bool:
    if node.tag in {"script", "style", "noscript", "svg", "canvas", "iframe", "table"}:
        return True
    return bool(node.classes() & SKIP_CLASSES)


def headline_text(node: HtmlNode) -> str:
    headline = find_first(node, lambda child: child.has_class("mw-headline"))
    return text_content(headline) if headline else ""


def has_block_children(node: HtmlNode) -> bool:
    return any(child.tag in BLOCK_TAGS for child in node.element_children())


def extract_message_lines(node: HtmlNode) -> list[tuple[str, str]]:
    messages: list[tuple[str, str]] = []
    containers = find_all(node, lambda child: child.has_class("NM-Container"))
    for container in containers:
        speaker_node = find_first(container, lambda child: child.has_class("SenderName"))
        text_node = find_first(
            container,
            lambda child: child.has_class("MessageLeft") or child.has_class("MessageRight"),
        )
        speaker = text_content(speaker_node) if speaker_node else ""
        text = text_content(text_node) if text_node else ""
        if speaker and text:
            messages.append((speaker, text))
    return messages


def render_branch_lines(node: HtmlNode) -> list[str]:
    renderer = StoryMarkdownRenderer()
    renderer.lines = []
    renderer.render_children(node.children)
    return [line for line in renderer.lines if line != ""]


def option_label(node: HtmlNode) -> str:
    image = find_first(node, lambda child: child.tag == "img" and bool(child.attr("alt")))
    alt = image.attr("alt") if image else ""
    match = re.search(r"剧情选项-图标-([^./]+)", alt)
    return match.group(1) if match else "选项"


def format_dialogue(speaker: str, text: str) -> str:
    return f"- **{speaker}**：{text}"


def tidy_markdown(lines: list[str]) -> str:
    output: list[str] = []
    blank = False
    for line in lines:
        if not line:
            if blank:
                continue
            blank = True
            output.append("")
            continue
        blank = False
        output.append(line.rstrip())
    return "\n".join(output).strip() + "\n"


def repair_standalone_dialogue_lines(lines: list[str]) -> list[str]:
    repaired: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not is_plain_speaker_line(line):
            repaired.append(line)
            index += 1
            continue

        next_index = index + 1
        blanks: list[str] = []
        while next_index < len(lines) and lines[next_index] == "":
            blanks.append(lines[next_index])
            next_index += 1

        if next_index < len(lines) and is_plain_dialogue_payload(lines[next_index]):
            repaired.append(format_dialogue(line.strip(), lines[next_index].strip()))
            index = next_index + 1
            continue

        repaired.append(line)
        repaired.extend(blanks)
        index = next_index

    return repaired


def is_plain_speaker_line(line: str) -> bool:
    value = line.strip()
    if not value or value not in DEFAULT_SPEAKER_HINTS:
        return False
    return line == value


def is_plain_dialogue_payload(line: str) -> bool:
    value = line.strip()
    if not value:
        return False
    if value.startswith(("#", "-", ">", "<!--")):
        return False
    if is_plain_speaker_line(value):
        return False
    return True
