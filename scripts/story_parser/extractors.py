from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from typing import Optional, Sequence, Tuple


HTML_HINT_RE = re.compile(r"<(?:html|body|div|span|p|table|script|article)\b", re.IGNORECASE)


def looks_like_html(text: str) -> bool:
    return bool(HTML_HINT_RE.search(text[:4096]))


class TextHTMLParser(HTMLParser):
    """Small fallback visible-text extractor."""

    BLOCK_TAGS = {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "dd",
        "div",
        "dl",
        "dt",
        "figcaption",
        "figure",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "td",
        "th",
        "tr",
        "ul",
    }
    SKIP_TAGS = {"script", "style", "noscript", "svg", "canvas", "iframe"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: Sequence[Tuple[str, Optional[str]]]) -> None:
        tag = tag.lower()
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
            return
        if tag in self.BLOCK_TAGS:
            self._newline()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
            return
        if tag in self.BLOCK_TAGS:
            self._newline()

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        text = html.unescape(data)
        if text.strip():
            self.parts.append(text)

    def _newline(self) -> None:
        if self.parts and self.parts[-1] != "\n":
            self.parts.append("\n")

    def text(self) -> str:
        return "".join(self.parts)


class HtmlTextExtractor:
    """Extract main visible text from complex wiki pages."""

    def extract(self, raw_html: str) -> str:
        bs4_text = self._extract_with_bs4(raw_html)
        if bs4_text is not None:
            return bs4_text

        parser = TextHTMLParser()
        parser.feed(raw_html)
        parser.close()
        return parser.text()

    def _extract_with_bs4(self, raw_html: str) -> Optional[str]:
        try:
            from bs4 import BeautifulSoup  # type: ignore
        except ImportError:
            return None

        soup = BeautifulSoup(raw_html, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "canvas", "iframe"]):
            tag.decompose()

        selectors = [
            "#mw-content-text",
            ".mw-parser-output",
            ".WikiaArticle",
            ".page-content",
            ".article-content",
            "article",
            "main",
            "body",
        ]

        root = None
        for selector in selectors:
            root = soup.select_one(selector)
            if root is not None:
                break
        root = root or soup

        for tag in root.select(
            ".navbox, .toc, .mw-editsection, .reference, .references, "
            ".printfooter, .catlinks, .metadata, .portable-infobox, "
            ".bili-list-style, .comment, .footer, .header"
        ):
            tag.decompose()

        return root.get_text("\n")
