from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from .config import settings
from .models import FetchedPage

_STRIP_TAGS = {
    "script", "style", "noscript", "head", "header", "footer",
    "nav", "aside", "form", "iframe", "svg", "button",
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; AI-Web-Search/0.1; +https://github.com/xsakix/ai-web-search)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def _clean_text(soup: BeautifulSoup) -> str:
    for tag in soup(list(_STRIP_TAGS)):
        tag.decompose()

    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _extract_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        full = urljoin(base_url, href)
        parsed = urlparse(full)
        if parsed.scheme in ("http", "https"):
            links.append(full)
    return list(dict.fromkeys(links))[:50]  # deduplicated, capped at 50


class PageFetcher:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            headers=_HEADERS,
            timeout=settings.http_timeout_seconds,
            follow_redirects=True,
            max_redirects=5,
        )

    async def fetch(self, url: str, extract_links: bool = False) -> FetchedPage:
        resp = await self._client.get(url)
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")

        if "text/html" not in content_type and "application/xhtml" not in content_type:
            # For non-HTML responses return raw text up to max_chars
            text = resp.text[: settings.fetch_max_chars]
            return FetchedPage(
                url=str(resp.url),
                text=text,
                status_code=resp.status_code,
                content_type=content_type,
            )

        soup = BeautifulSoup(resp.text, "lxml")

        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else None

        text = _clean_text(soup)
        text = text[: settings.fetch_max_chars]

        links = _extract_links(soup, str(resp.url)) if extract_links else []

        return FetchedPage(
            url=str(resp.url),
            title=title,
            text=text,
            links=links,
            status_code=resp.status_code,
            content_type=content_type,
        )

    async def aclose(self) -> None:
        await self._client.aclose()
