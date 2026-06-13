from __future__ import annotations

import html
import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Iterable


BILIGAME_HOST = "wiki.biligame.com"
DETAIL_HINT = "详细对话内容"
NEXT_HINT_RE = re.compile(r"(下一|下一个|后一|后续|继续)")


@dataclass(frozen=True)
class StoryLink:
    url: str
    title: str
    link_type: str
    label: str


@dataclass
class BwikiPageInfo:
    url: str
    title: str = ""
    version: str | None = None
    links: list[StoryLink] = field(default_factory=list)


def extract_bwiki_page_info(raw_html: str, base_url: str) -> BwikiPageInfo:
    """Extract title, version and task relation links from a BWiki story page."""

    info = BwikiPageInfo(
        url=normalize_bwiki_url(base_url, base_url) or base_url,
        title=extract_title(raw_html),
        version=extract_infobox_field(raw_html, "所属版本"),
    )
    info.links.extend(extract_section_links(raw_html, base_url, "任务条件", "requires"))
    info.links.extend(extract_section_links(raw_html, base_url, "后续任务", "next_task"))
    info.links.extend(extract_section_links(raw_html, base_url, "系列任务", "series"))
    info.links = dedupe_story_links(info.links)
    return info


def extract_title(raw_html: str) -> str:
    for pattern in (
        r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)["\']',
        r'<h1[^>]*id=["\']firstHeading["\'][^>]*>(.*?)</h1>',
        r"<title[^>]*>(.*?)</title>",
    ):
        match = re.search(pattern, raw_html, re.IGNORECASE | re.DOTALL)
        if match:
            title = strip_tags(match.group(1))
            title = re.sub(r"_BWIKI.*$", "", title).strip()
            if title:
                return title
    return ""


def extract_infobox_field(raw_html: str, field_name: str) -> str | None:
    pattern = re.compile(
        rf"<th[^>]*>\s*{re.escape(field_name)}\s*</th>\s*<td[^>]*>(.*?)</td>",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(raw_html)
    if not match:
        return None
    value = strip_tags(match.group(1))
    value = re.sub(r"\s+", " ", value).strip()
    return value or None


def extract_section_links(raw_html: str, base_url: str, section_id: str, link_type: str) -> list[StoryLink]:
    section = extract_headline_section(raw_html, section_id)
    if not section:
        return []

    links: list[StoryLink] = []
    for href, text, title in iter_anchor_tags(section):
        resolved = normalize_bwiki_url(href, base_url)
        if not resolved:
            continue
        link_title = (title or text).strip()
        links.append(
            StoryLink(
                url=resolved,
                title=link_title,
                link_type=link_type,
                label=section_id,
            )
        )
    return links


def extract_headline_section(raw_html: str, section_id: str) -> str:
    headline_re = re.compile(
        rf'<span\s+class=["\']mw-headline["\']\s+id=["\']{re.escape(section_id)}["\'][^>]*>.*?</span>',
        re.IGNORECASE | re.DOTALL,
    )
    match = headline_re.search(raw_html)
    if not match:
        return ""

    start = match.end()
    next_heading = re.search(r"<h[23]\b", raw_html[start:], re.IGNORECASE)
    end = start + next_heading.start() if next_heading else len(raw_html)
    return raw_html[start:end]


def iter_anchor_tags(raw_html: str) -> Iterable[tuple[str, str, str]]:
    anchor_re = re.compile(
        r"<a\s+([^>]*?href=[\"'][^\"']+[\"'][^>]*)>(.*?)</a>",
        re.IGNORECASE | re.DOTALL,
    )
    for match in anchor_re.finditer(raw_html):
        attrs = match.group(1)
        href_match = re.search(r"href=[\"']([^\"']+)[\"']", attrs, re.IGNORECASE)
        if not href_match:
            continue
        title_match = re.search(r"title=[\"']([^\"']+)[\"']", attrs, re.IGNORECASE)
        yield (
            html.unescape(href_match.group(1)),
            strip_tags(match.group(2)),
            html.unescape(title_match.group(1)) if title_match else "",
        )


def strip_tags(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value)
    return html.unescape(value).strip()


def find_bwiki_detail_links(raw_html: str, base_url: str) -> list[str]:
    """Find BWiki task detail pages linked from a task-series overview page."""

    links = _find_bwiki_detail_links_bs4(raw_html, base_url)
    if not links:
        links = _find_bwiki_detail_links_regex(raw_html, base_url)
    return dedupe_preserve_order(links)


def find_bwiki_story_links(raw_html: str, base_url: str) -> list[str]:
    """Find BWiki story links worth mirroring.

    This is intentionally conservative. It follows:
    - overview links near "详细对话内容"
    - links whose own text or immediate parent text looks like a next-story link
    """

    links = _find_bwiki_story_links_bs4(raw_html, base_url)
    if not links:
        links = _find_bwiki_story_links_regex(raw_html, base_url)
    return dedupe_preserve_order(links)


def dedupe_story_links(values: Iterable[StoryLink]) -> list[StoryLink]:
    seen: set[tuple[str, str]] = set()
    result: list[StoryLink] = []
    for value in values:
        key = (value.url, value.link_type)
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _find_bwiki_detail_links_bs4(raw_html: str, base_url: str) -> list[str]:
    try:
        from bs4 import BeautifulSoup  # type: ignore
    except ImportError:
        return []

    soup = BeautifulSoup(raw_html, "html.parser")
    links: list[str] = []

    for anchor in soup.find_all("a", href=True):
        parent = anchor.parent
        parent_text = parent.get_text(" ", strip=True) if parent is not None else ""
        if DETAIL_HINT not in parent_text:
            continue

        href = anchor.get("href")
        if not href:
            continue
        resolved = normalize_bwiki_url(href, base_url)
        if resolved:
            links.append(resolved)

    return links


def _find_bwiki_story_links_bs4(raw_html: str, base_url: str) -> list[str]:
    try:
        from bs4 import BeautifulSoup  # type: ignore
    except ImportError:
        return []

    soup = BeautifulSoup(raw_html, "html.parser")
    links: list[str] = []

    for anchor in soup.find_all("a", href=True):
        text = anchor.get_text(" ", strip=True)
        parent = anchor.parent
        parent_text = parent.get_text(" ", strip=True) if parent is not None else ""
        context = f"{text} {parent_text}"
        if DETAIL_HINT not in context and not NEXT_HINT_RE.search(context):
            continue

        resolved = normalize_bwiki_url(anchor.get("href") or "", base_url)
        if resolved:
            links.append(resolved)

    return links


def _find_bwiki_detail_links_regex(raw_html: str, base_url: str) -> list[str]:
    links: list[str] = []
    pattern = re.compile(
        rf"{re.escape(DETAIL_HINT)}.*?<a\s+[^>]*href=[\"']([^\"']+)[\"'][^>]*>",
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(raw_html):
        resolved = normalize_bwiki_url(match.group(1), base_url)
        if resolved:
            links.append(resolved)
    return links


def _find_bwiki_story_links_regex(raw_html: str, base_url: str) -> list[str]:
    links: list[str] = []
    anchor_re = re.compile(
        r"<a\s+[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
        re.IGNORECASE | re.DOTALL,
    )
    for match in anchor_re.finditer(raw_html):
        start = max(0, match.start() - 120)
        end = min(len(raw_html), match.end() + 120)
        context = re.sub(r"<[^>]+>", "", raw_html[start:end])
        if DETAIL_HINT not in context and not NEXT_HINT_RE.search(context):
            continue
        resolved = normalize_bwiki_url(match.group(1), base_url)
        if resolved:
            links.append(resolved)
    return links


def normalize_bwiki_url(href: str, base_url: str) -> str | None:
    if href.startswith("#"):
        return None

    resolved = urllib.parse.urljoin(base_url, href)
    parsed = urllib.parse.urlparse(resolved)
    if parsed.netloc != BILIGAME_HOST:
        return None
    if not parsed.path.startswith("/sr/"):
        return None

    return urllib.parse.urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, "", parsed.query, "")
    )


def dedupe_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
