from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse

import os

import httpx

from ..models import ImageResult, SafeSearch, SearchResult, TimeRange
from .base import SearchProvider

_BASE = "https://api.search.brave.com/res/v1"

_SAFE_MAP = {
    SafeSearch.off: "off",
    SafeSearch.moderate: "moderate",
    SafeSearch.strict: "strict",
}

_FRESH_MAP = {
    TimeRange.day: "pd",
    TimeRange.week: "pw",
    TimeRange.month: "pm",
    TimeRange.year: "py",
}


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc
    except Exception:
        return ""


class BraveProvider(SearchProvider):
    name = "brave"

    def is_available(self) -> bool:
        return bool(os.environ.get("BRAVE_API_KEY", ""))

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": os.environ.get("BRAVE_API_KEY", ""),
        }

    async def search(
        self,
        query: str,
        num_results: int = 10,
        region: str = "us",
        safe_search: SafeSearch = SafeSearch.moderate,
    ) -> list[SearchResult]:
        params = {
            "q": query,
            "count": min(num_results, 20),
            "country": region[:2] if region != "wt-wt" else "us",
            "safesearch": _SAFE_MAP[safe_search],
            "text_decorations": False,
        }
        async with httpx.AsyncClient(timeout=float(os.environ.get("HTTP_TIMEOUT_SECONDS", "15"))) as client:
            resp = await client.get(
                f"{_BASE}/web/search", headers=self._headers(), params=params
            )
            resp.raise_for_status()
            data = resp.json()

        web = data.get("web", {}).get("results", [])
        return [
            SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                snippet=r.get("description", ""),
                published_date=r.get("page_age"),
                source=_domain(r.get("url", "")),
            )
            for r in web
        ]

    async def search_news(
        self,
        query: str,
        num_results: int = 10,
        time_range: Optional[TimeRange] = None,
        region: str = "us",
    ) -> list[SearchResult]:
        params: dict = {
            "q": query,
            "count": min(num_results, 20),
            "country": region[:2] if region != "wt-wt" else "us",
        }
        if time_range:
            params["freshness"] = _FRESH_MAP[time_range]

        async with httpx.AsyncClient(timeout=float(os.environ.get("HTTP_TIMEOUT_SECONDS", "15"))) as client:
            resp = await client.get(
                f"{_BASE}/news/search", headers=self._headers(), params=params
            )
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results", [])
        return [
            SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                snippet=r.get("description", ""),
                published_date=r.get("age"),
                source=r.get("meta_url", {}).get("netloc") or _domain(r.get("url", "")),
            )
            for r in results
        ]

    async def search_images(
        self,
        query: str,
        num_results: int = 10,
        region: str = "us",
        safe_search: SafeSearch = SafeSearch.moderate,
    ) -> list[ImageResult]:
        params = {
            "q": query,
            "count": min(num_results, 20),
            "safesearch": _SAFE_MAP[safe_search],
        }
        async with httpx.AsyncClient(timeout=float(os.environ.get("HTTP_TIMEOUT_SECONDS", "15"))) as client:
            resp = await client.get(
                f"{_BASE}/images/search", headers=self._headers(), params=params
            )
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results", [])
        return [
            ImageResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                image_url=r.get("thumbnail", {}).get("src", ""),
                width=r.get("properties", {}).get("width"),
                height=r.get("properties", {}).get("height"),
                source=_domain(r.get("url", "")),
            )
            for r in results
        ]
