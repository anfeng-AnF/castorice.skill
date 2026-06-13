from __future__ import annotations

import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0 Safari/537.36 CastoriceStoryParser/1.0"
)

DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
    "Referer": "https://wiki.biligame.com/sr/",
    "Connection": "close",
}


def read_text(path: Path) -> str:
    """Read text with common encodings used by copied web pages."""

    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def detect_charset(content_type: str) -> Optional[str]:
    match = re.search(r"charset=([\w\-]+)", content_type or "", re.IGNORECASE)
    return match.group(1) if match else None


def safe_cache_name(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    base = f"{parsed.netloc}{parsed.path}"
    if parsed.query:
        base += "?" + parsed.query
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("_")
    return (base[:180] or "page") + ".html"


class SourceFetcher:
    """Fetch URLs and read local files with optional HTML caching."""

    def __init__(
        self,
        cache_dir: Optional[Path],
        timeout: int = 30,
        retries: int = 3,
        retry_sleep: float = 1.5,
    ) -> None:
        self.cache_dir = cache_dir
        self.timeout = timeout
        self.retries = retries
        self.retry_sleep = retry_sleep

    def fetch_url(self, url: str) -> str:
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path = self.cache_dir / safe_cache_name(url)
            if cache_path.exists():
                return read_text(cache_path)

        request = urllib.request.Request(url, headers=DEFAULT_HEADERS)
        last_error: Optional[BaseException] = None

        for attempt in range(1, self.retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = response.read()
                    charset = detect_charset(response.headers.get("Content-Type", "")) or "utf-8"
                    text = raw.decode(charset, errors="replace")
                    if self.cache_dir:
                        (self.cache_dir / safe_cache_name(url)).write_text(text, encoding="utf-8")
                    return text
            except (urllib.error.URLError, TimeoutError) as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(self.retry_sleep)

        raise RuntimeError(f"failed to fetch {url}: {last_error}")

    def read_source(self, source: str) -> str:
        if source.startswith("http://") or source.startswith("https://"):
            return self.fetch_url(source)
        return read_text(Path(source))


def load_url_file(path: Path) -> list[str]:
    urls: list[str] = []
    for raw_line in read_text(path).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line)
    return urls
