from __future__ import annotations

import asyncio
from typing import Optional
from urllib.parse import urlparse

from ddgs import DDGS
from ddgs.exceptions import DDGSException, RatelimitException, TimeoutException

from ..models import ImageResult, SafeSearch, SearchResult, TimeRange
from .base import SearchProvider

_SAFE_MAP = {
    SafeSearch.off: "off",
    SafeSearch.moderate: "moderate",
    SafeSearch.strict: "strict",
}

_TIME_MAP = {
    TimeRange.day: "d",
    TimeRange.week: "w",
    TimeRange.month: "m",
    TimeRange.year: "y",
}


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc
    except Exception:
        return ""


class DuckDuckGoProvider(SearchProvider):
    name = "duckduckgo"

    def is_available(self) -> bool:
        return True  # no API key required

    async def search(
        self,
        query: str,
        num_results: int = 10,
        region: str = "wt-wt",
        safe_search: SafeSearch = SafeSearch.moderate,
    ) -> list[SearchResult]:
        def _run() -> list[SearchResult]:
            with DDGS() as d:
                raw = d.text(
                    query,
                    region=region,
                    safesearch=_SAFE_MAP[safe_search],
                    max_results=num_results,
                    backend="duckduckgo",
                )
            return [
                SearchResult(
                    title=r.get("title", ""),
                    url=r.get("href", ""),
                    snippet=r.get("body", ""),
                    source=_domain(r.get("href", "")),
                )
                for r in (raw or [])
            ]

        try:
            return await asyncio.to_thread(_run)
        except RatelimitException as exc:
            raise RuntimeError(f"DuckDuckGo rate limit reached: {exc}") from exc
        except TimeoutException as exc:
            raise RuntimeError(f"DuckDuckGo request timed out: {exc}") from exc
        except DDGSException as exc:
            raise RuntimeError(f"DuckDuckGo search error: {exc}") from exc

    async def search_news(
        self,
        query: str,
        num_results: int = 10,
        time_range: Optional[TimeRange] = None,
        region: str = "wt-wt",
    ) -> list[SearchResult]:
        timelimit = _TIME_MAP.get(time_range) if time_range else None

        def _run() -> list[SearchResult]:
            with DDGS() as d:
                raw = d.news(
                    query,
                    region=region,
                    timelimit=timelimit,
                    max_results=num_results,
                )
            return [
                SearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("body", ""),
                    published_date=r.get("date"),
                    source=r.get("source") or _domain(r.get("url", "")),
                )
                for r in (raw or [])
            ]

        try:
            return await asyncio.to_thread(_run)
        except RatelimitException as exc:
            raise RuntimeError(f"DuckDuckGo rate limit reached: {exc}") from exc
        except TimeoutException as exc:
            raise RuntimeError(f"DuckDuckGo request timed out: {exc}") from exc
        except DDGSException as exc:
            raise RuntimeError(f"DuckDuckGo search error: {exc}") from exc

    async def search_images(
        self,
        query: str,
        num_results: int = 10,
        region: str = "wt-wt",
        safe_search: SafeSearch = SafeSearch.moderate,
    ) -> list[ImageResult]:
        def _run() -> list[ImageResult]:
            with DDGS() as d:
                raw = d.images(
                    query,
                    region=region,
                    safesearch=_SAFE_MAP[safe_search],
                    max_results=num_results,
                )
            return [
                ImageResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    image_url=r.get("image", ""),
                    width=r.get("width"),
                    height=r.get("height"),
                    source=_domain(r.get("url", "")),
                )
                for r in (raw or [])
            ]

        try:
            return await asyncio.to_thread(_run)
        except RatelimitException as exc:
            raise RuntimeError(f"DuckDuckGo rate limit reached: {exc}") from exc
        except TimeoutException as exc:
            raise RuntimeError(f"DuckDuckGo request timed out: {exc}") from exc
        except DDGSException as exc:
            raise RuntimeError(f"DuckDuckGo search error: {exc}") from exc
