"""Async web crawler with robots.txt compliance and politeness controls."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_CRAWL_HEADERS = {
    "User-Agent": "AIWebSearchBot/0.1 (+https://github.com/xsakix/ai-web-search)",
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

_BLOCKED_EXTENSIONS = frozenset(
    ".pdf .doc .docx .xls .xlsx .ppt .pptx .zip .tar .gz .rar "
    ".mp3 .mp4 .avi .mov .wmv .flv .jpg .jpeg .png .gif .webp .svg "
    ".css .js .json .xml .rss .atom".split()
)


@dataclass
class CrawlResult:
    url: str
    status_code: int
    title: str = ""
    body: str = ""
    description: str = ""
    links: list[str] = field(default_factory=list)
    error: str = ""


def _is_crawlable(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    path = parsed.path.lower()
    if any(path.endswith(ext) for ext in _BLOCKED_EXTENSIONS):
        return False
    return True


def _extract_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        full = urljoin(base_url, href)
        # Normalise: drop fragment
        parsed = urlparse(full)
        clean = parsed._replace(fragment="").geturl()
        if _is_crawlable(clean):
            links.append(clean)
    # Deduplicate while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for link in links:
        if link not in seen:
            seen.add(link)
            out.append(link)
    return out


def _extract_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "head", "nav",
                     "header", "footer", "aside", "form", "iframe", "svg"]):
        tag.decompose()
    import re
    text = soup.get_text(separator=" ", strip=True)
    return re.sub(r"\s{2,}", " ", text).strip()


class RobotsCache:
    """In-process cache of robots.txt rules per domain."""

    def __init__(self, user_agent: str = "AIWebSearchBot") -> None:
        self._cache: dict[str, RobotFileParser] = {}
        self._ua = user_agent

    async def can_fetch(self, client: httpx.AsyncClient, url: str) -> bool:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._cache:
            rp = RobotFileParser()
            robots_url = f"{origin}/robots.txt"
            try:
                resp = await client.get(robots_url, timeout=5)
                rp.parse(resp.text.splitlines())
            except Exception:
                rp.allow_all = True
            self._cache[origin] = rp
        return self._cache[origin].can_fetch(self._ua, url)


class Crawler:
    def __init__(
        self,
        timeout: float = 15.0,
        crawl_delay: float = 1.0,
        max_body_chars: int = 50_000,
    ) -> None:
        self._timeout = timeout
        self._crawl_delay = crawl_delay
        self._max_body_chars = max_body_chars
        self._robots = RobotsCache()
        self._client = httpx.AsyncClient(
            headers=_CRAWL_HEADERS,
            timeout=timeout,
            follow_redirects=True,
            max_redirects=5,
        )
        # Per-domain rate limiting: track last fetch time
        self._domain_last_fetch: dict[str, float] = {}

    async def _wait_for_politeness(self, domain: str) -> None:
        last = self._domain_last_fetch.get(domain, 0.0)
        now = asyncio.get_event_loop().time()
        wait = self._crawl_delay - (now - last)
        if wait > 0:
            await asyncio.sleep(wait)

    async def fetch(self, url: str) -> CrawlResult:
        if not _is_crawlable(url):
            return CrawlResult(url=url, status_code=0, error="URL not crawlable")

        domain = urlparse(url).netloc

        if not await self._robots.can_fetch(self._client, url):
            return CrawlResult(url=url, status_code=0, error="Blocked by robots.txt")

        await self._wait_for_politeness(domain)
        self._domain_last_fetch[domain] = asyncio.get_event_loop().time()

        try:
            resp = await self._client.get(url)
        except httpx.TimeoutException:
            return CrawlResult(url=url, status_code=0, error="Timeout")
        except httpx.RequestError as exc:
            return CrawlResult(url=url, status_code=0, error=str(exc))

        content_type = resp.headers.get("content-type", "")
        if "text/html" not in content_type and "application/xhtml" not in content_type:
            return CrawlResult(url=str(resp.url), status_code=resp.status_code,
                               error=f"Non-HTML content-type: {content_type}")

        if resp.status_code >= 400:
            return CrawlResult(url=str(resp.url), status_code=resp.status_code,
                               error=f"HTTP {resp.status_code}")

        soup = BeautifulSoup(resp.text, "lxml")

        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else ""

        meta_desc = soup.find("meta", attrs={"name": "description"})
        description = ""
        if meta_desc and meta_desc.get("content"):
            description = meta_desc["content"].strip()

        body = _extract_text(soup)[: self._max_body_chars]
        links = _extract_links(soup, str(resp.url))

        return CrawlResult(
            url=str(resp.url),
            status_code=resp.status_code,
            title=title,
            body=body,
            description=description,
            links=links,
        )

    async def aclose(self) -> None:
        await self._client.aclose()
