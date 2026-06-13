from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Callable, Iterable


VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}

SKIP_TEXT_TAGS = {"script", "style", "noscript", "svg", "canvas", "iframe"}
SKIP_TEXT_CLASSES = {"mw-editsection", "plotIcon", "resourceLoader"}


@dataclass
class HtmlNode:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list["HtmlNode"] = field(default_factory=list)
    text: str = ""
    parent: "HtmlNode | None" = None

    def attr(self, name: str, default: str = "") -> str:
        return self.attrs.get(name, default)

    def classes(self) -> set[str]:
        return {item for item in self.attr("class").split() if item}

    def has_class(self, class_name: str) -> bool:
        return class_name in self.classes()

    def append(self, child: "HtmlNode") -> None:
        child.parent = self
        self.children.append(child)

    def element_children(self) -> list["HtmlNode"]:
        return [child for child in self.children if child.tag != "#text"]


class HtmlTreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = HtmlNode("document")
        self.stack: list[HtmlNode] = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        node = HtmlNode(tag=tag, attrs={key: value or "" for key, value in attrs})
        self.stack[-1].append(node)
        if tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        node = HtmlNode(tag=tag, attrs={key: value or "" for key, value in attrs})
        self.stack[-1].append(node)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if data:
            self.stack[-1].append(HtmlNode(tag="#text", text=data))


def parse_html(raw_html: str) -> HtmlNode:
    parser = HtmlTreeBuilder()
    parser.feed(raw_html)
    parser.close()
    return parser.root


def descendants(node: HtmlNode) -> Iterable[HtmlNode]:
    for child in node.children:
        yield child
        yield from descendants(child)


def find_first(node: HtmlNode, predicate: Callable[[HtmlNode], bool]) -> HtmlNode | None:
    if predicate(node):
        return node
    for child in node.children:
        found = find_first(child, predicate)
        if found is not None:
            return found
    return None


def find_all(node: HtmlNode, predicate: Callable[[HtmlNode], bool]) -> list[HtmlNode]:
    result: list[HtmlNode] = []
    if predicate(node):
        result.append(node)
    for child in node.children:
        result.extend(find_all(child, predicate))
    return result


def text_content(node: HtmlNode) -> str:
    text = _text_content(node)
    text = html.unescape(text)
    text = text.replace("\u00a0", " ").replace("\u3000", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n+", "\n", text)
    return text.strip()


def _text_content(node: HtmlNode) -> str:
    if node.tag == "#text":
        return node.text
    if node.tag in SKIP_TEXT_TAGS or node.tag == "img":
        return ""
    if node.classes() & SKIP_TEXT_CLASSES:
        return ""
    if node.tag == "br":
        return "\n"
    if node.tag == "ruby":
        rb = "".join(text_content(child) for child in node.children if child.tag == "rb").strip()
        rt = "".join(text_content(child) for child in node.children if child.tag == "rt").strip()
        if rb and rt:
            return f"{rb}（{rt}）"
        return rb or rt
    return "".join(_text_content(child) for child in node.children)

