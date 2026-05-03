"""AI Web Search – MCP Server.

Exposes a self-hosted web search engine over the Model Context Protocol.
The engine crawls, indexes, and searches web content locally using BM25 ranking.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .config import settings
from .engine import CrawlReport, Crawler, Indexer, QueryProcessor, Storage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP(
    "ai-web-search",
    instructions=(
        "A self-hosted web search engine. "
        "Use `crawl_url` to add pages to the index, then `search` to query them. "
        "Use `get_stats` to inspect the current index, `list_domains` to see what "
        "has been crawled, and `peek_document` to retrieve the raw text of any "
        "indexed page."
    ),
)

# Singleton engine components — shared across tool calls within one server process
_storage = Storage(db_path=settings.index_db_path)
_crawler = Crawler(
    timeout=settings.http_timeout_seconds,
    crawl_delay=settings.crawl_delay_seconds,
    max_body_chars=settings.max_body_chars,
)
_indexer = Indexer(storage=_storage, crawler=_crawler)
_query = QueryProcessor(storage=_storage)


# ── Tools ─────────────────────────────────────────────────────────────────────


@mcp.tool()
async def crawl_url(
    url: str,
    max_pages: int = 10,
    max_depth: int = 1,
    same_domain_only: bool = True,
) -> dict:
    """Crawl a URL (and its linked pages) and add them to the search index.

    Args:
        url: The seed URL to start crawling from.
        max_pages: Maximum number of pages to crawl (default 10, max 200).
        max_depth: How many link-hops away from the seed to follow (0 = seed only).
        same_domain_only: If True (default), only follow links on the same domain.

    Returns:
        A report with counts of pages crawled, failed, and skipped.
    """
    max_pages = max(1, min(200, max_pages))
    max_depth = max(0, min(5, max_depth))

    report: CrawlReport = await _indexer.crawl_and_index(
        seed_url=url,
        max_pages=max_pages,
        max_depth=max_depth,
        same_domain_only=same_domain_only,
    )
    return {
        "seed_url": report.seed_url,
        "pages_crawled": report.pages_crawled,
        "pages_failed": report.pages_failed,
        "pages_skipped": report.pages_skipped,
        "indexed_urls": report.indexed_urls,
        "errors": report.errors,
    }


@mcp.tool()
def search(query: str, top_k: int = 10) -> dict:
    """Search the local index using BM25 ranking.

    Args:
        query: Free-text search query.
        top_k: Number of results to return (default 10, max 50).

    Returns:
        Ranked list of matching documents with title, URL, snippet, and score.
    """
    top_k = max(1, min(50, top_k))
    results = _query.search(query, top_k=top_k)
    return {
        "query": results.query,
        "total_docs_in_index": results.total_docs,
        "elapsed_ms": results.elapsed_ms,
        "hits": [
            {
                "url": h.url,
                "title": h.title,
                "snippet": h.snippet,
                "score": h.score,
                "domain": h.domain,
                "word_count": h.word_count,
            }
            for h in results.hits
        ],
    }


@mcp.tool()
def get_stats() -> dict:
    """Return statistics about the current search index."""
    queue_stats = _storage.queue_stats()
    return {
        "documents_indexed": _storage.document_count(),
        "average_document_length_words": round(_storage.avg_word_count(), 1),
        "crawl_queue": queue_stats,
        "index_db_path": str(settings.index_db_path),
    }


@mcp.tool()
def list_domains(limit: int = 20) -> list[dict]:
    """List the domains present in the index with their document counts.

    Args:
        limit: Maximum number of domains to return (default 20).
    """
    return _storage.domain_stats()[:limit]


@mcp.tool()
def peek_document(url: str) -> dict:
    """Retrieve the full indexed text of a specific URL.

    Args:
        url: The exact URL to look up in the index.
    """
    doc = _storage.get_document_by_url(url)
    if doc is None:
        return {"error": f"URL not found in index: {url}"}
    return {
        "url": doc.url,
        "title": doc.title,
        "description": doc.description,
        "body": doc.body[:settings.fetch_max_chars],
        "word_count": doc.word_count,
        "domain": doc.domain,
        "crawled_at": doc.crawled_at,
    }


# ── Resource ──────────────────────────────────────────────────────────────────


@mcp.resource("search://config")
def get_config() -> str:
    """Current server configuration."""
    return (
        f"Index DB: {settings.index_db_path}\n"
        f"Crawl delay: {settings.crawl_delay_seconds}s\n"
        f"Max body chars: {settings.max_body_chars}\n"
        f"HTTP timeout: {settings.http_timeout_seconds}s\n"
        f"Documents indexed: {_storage.document_count()}"
    )


# ── Entry point ────────────────────────────────────────────────────────────────


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
