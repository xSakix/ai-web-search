"""AI Web Search – MCP Server entry point."""

from __future__ import annotations

import asyncio
import time
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .cache import SearchCache
from .config import settings
from .fetcher import PageFetcher
from .models import SafeSearch, SearchResponse, TimeRange
from .providers import ProviderRegistry

mcp = FastMCP(
    "ai-web-search",
    instructions=(
        "A web search engine. Use `web_search` for general queries, "
        "`search_news` for recent news, `fetch_page` to read a specific URL, "
        "and `batch_search` to run multiple queries in parallel."
    ),
)

_registry = ProviderRegistry()
_cache = SearchCache(maxsize=settings.cache_max_size, ttl=settings.cache_ttl_seconds)
_fetcher = PageFetcher()


# ─── Tools ────────────────────────────────────────────────────────────────────


@mcp.tool()
async def web_search(
    query: str,
    num_results: int = 10,
    region: str = "wt-wt",
    safe_search: SafeSearch = SafeSearch.moderate,
    provider: Optional[str] = None,
) -> dict:
    """Search the web and return a ranked list of results.

    Args:
        query: The search query string.
        num_results: Number of results to return (1-20, default 10).
        region: Region code, e.g. "us-en", "gb-en", "wt-wt" (worldwide).
        safe_search: Safe search level – "off", "moderate", or "strict".
        provider: Force a specific provider ("duckduckgo" or "brave").
                  Defaults to the highest-priority available provider.
    """
    num_results = max(1, min(20, num_results))
    cache_params = {
        "query": query,
        "num_results": num_results,
        "region": region,
        "safe_search": safe_search.value,
        "provider": provider or "auto",
    }
    cached = _cache.get("web_search", cache_params)
    if cached:
        cached["cached"] = True
        return cached

    p = _registry.get(provider) if provider else _registry.primary
    if p is None:
        return {"error": f"Provider '{provider}' is not available."}

    t0 = time.perf_counter()
    results = await p.search(query, num_results=num_results, region=region, safe_search=safe_search)
    elapsed = (time.perf_counter() - t0) * 1000

    response = SearchResponse(
        query=query,
        provider=p.name,
        results=results,
        cached=False,
        elapsed_ms=round(elapsed, 1),
    ).model_dump()

    _cache.set("web_search", cache_params, response)
    return response


@mcp.tool()
async def search_news(
    query: str,
    num_results: int = 10,
    time_range: Optional[TimeRange] = None,
    region: str = "wt-wt",
    provider: Optional[str] = None,
) -> dict:
    """Search for recent news articles.

    Args:
        query: The news search query.
        num_results: Number of articles to return (1-20, default 10).
        time_range: Filter by recency – "day", "week", "month", or "year".
        region: Region code for localised results.
        provider: Force a specific provider.
    """
    num_results = max(1, min(20, num_results))
    cache_params = {
        "query": query,
        "num_results": num_results,
        "time_range": time_range.value if time_range else None,
        "region": region,
        "provider": provider or "auto",
    }
    cached = _cache.get("search_news", cache_params)
    if cached:
        cached["cached"] = True
        return cached

    p = _registry.get(provider) if provider else _registry.primary
    if p is None:
        return {"error": f"Provider '{provider}' is not available."}

    t0 = time.perf_counter()
    results = await p.search_news(query, num_results=num_results, time_range=time_range, region=region)
    elapsed = (time.perf_counter() - t0) * 1000

    response = SearchResponse(
        query=query,
        provider=p.name,
        results=results,
        cached=False,
        elapsed_ms=round(elapsed, 1),
    ).model_dump()

    _cache.set("search_news", cache_params, response)
    return response


@mcp.tool()
async def search_images(
    query: str,
    num_results: int = 10,
    region: str = "wt-wt",
    safe_search: SafeSearch = SafeSearch.moderate,
    provider: Optional[str] = None,
) -> dict:
    """Search for images and return metadata (title, URL, thumbnail, dimensions).

    Args:
        query: The image search query.
        num_results: Number of results to return (1-20, default 10).
        region: Region code for localised results.
        safe_search: Safe search filter level.
        provider: Force a specific provider.
    """
    num_results = max(1, min(20, num_results))
    cache_params = {
        "query": query,
        "num_results": num_results,
        "region": region,
        "safe_search": safe_search.value,
        "provider": provider or "auto",
    }
    cached = _cache.get("search_images", cache_params)
    if cached:
        cached["cached"] = True
        return cached

    p = _registry.get(provider) if provider else _registry.primary
    if p is None:
        return {"error": f"Provider '{provider}' is not available."}

    t0 = time.perf_counter()
    results = await p.search_images(query, num_results=num_results, region=region, safe_search=safe_search)
    elapsed = (time.perf_counter() - t0) * 1000

    response = {
        "query": query,
        "provider": p.name,
        "results": [r.model_dump() for r in results],
        "cached": False,
        "elapsed_ms": round(elapsed, 1),
    }
    _cache.set("search_images", cache_params, response)
    return response


@mcp.tool()
async def fetch_page(
    url: str,
    extract_links: bool = False,
    max_chars: Optional[int] = None,
) -> dict:
    """Fetch a web page and return its cleaned text content.

    Args:
        url: The URL to fetch.
        extract_links: If True, also return a list of hyperlinks found on the page.
        max_chars: Maximum characters of text to return (default from config).
    """
    cache_params = {"url": url, "extract_links": extract_links}
    cached = _cache.get("fetch_page", cache_params)
    if cached:
        return cached

    page = await _fetcher.fetch(url, extract_links=extract_links)
    result = page.model_dump()

    if max_chars and max_chars < len(result.get("text", "")):
        result["text"] = result["text"][:max_chars]

    _cache.set("fetch_page", cache_params, result)
    return result


@mcp.tool()
async def batch_search(
    queries: list[str],
    num_results: int = 5,
    region: str = "wt-wt",
    safe_search: SafeSearch = SafeSearch.moderate,
) -> list[dict]:
    """Run multiple web searches in parallel and return all results.

    Args:
        queries: List of search query strings (max 10).
        num_results: Results per query (1-10, default 5).
        region: Region code applied to all queries.
        safe_search: Safe search level applied to all queries.
    """
    queries = queries[:10]
    num_results = max(1, min(10, num_results))

    tasks = [
        web_search(q, num_results=num_results, region=region, safe_search=safe_search)
        for q in queries
    ]
    return list(await asyncio.gather(*tasks))


# ─── Resources ────────────────────────────────────────────────────────────────


@mcp.resource("search://config")
def get_config() -> str:
    """Current server configuration and available providers."""
    return (
        f"Available providers: {', '.join(_registry.available)}\n"
        f"Primary provider: {_registry.primary.name}\n"
        f"Cache TTL: {settings.cache_ttl_seconds}s  |  "
        f"Cache size: {_cache.size}/{settings.cache_max_size}\n"
        f"HTTP timeout: {settings.http_timeout_seconds}s\n"
        f"Max fetch chars: {settings.fetch_max_chars}"
    )


# ─── Entry point ──────────────────────────────────────────────────────────────


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
