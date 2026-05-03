"""End-to-end indexer tests using an in-memory store and a mock crawler."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from ai_web_search.engine.crawler import CrawlResult, Crawler
from ai_web_search.engine.indexer import Indexer
from ai_web_search.engine.storage import Storage

SAMPLE_HTML = """
<html><head><title>Python Docs</title>
<meta name="description" content="Python documentation">
</head><body>
<p>Python is a great programming language with clean syntax.</p>
<a href="/tutorial">Tutorial</a>
<a href="https://pypi.org/">PyPI</a>
</body></html>
"""


def _make_indexer() -> tuple[Storage, Indexer]:
    store = Storage(":memory:")
    crawler = MagicMock(spec=Crawler)
    indexer = Indexer(storage=store, crawler=crawler)
    return store, indexer


def test_index_crawl_result_stores_document():
    store, indexer = _make_indexer()
    result = CrawlResult(
        url="https://python.org",
        status_code=200,
        title="Python",
        body="Python is a programming language",
        description="Official site",
    )
    ir = indexer.index_crawl_result(result)

    assert ir.indexed is True
    assert ir.doc_id > 0
    assert ir.word_count > 0

    doc = store.get_document(ir.doc_id)
    assert doc.url == "https://python.org"
    assert doc.title == "Python"


def test_index_crawl_result_writes_postings():
    store, indexer = _make_indexer()
    result = CrawlResult(
        url="https://example.com",
        status_code=200,
        title="BM25 Search",
        body="inverted index bm25 ranking relevance",
    )
    ir = indexer.index_crawl_result(result)

    postings = store.get_postings("bm25")
    assert len(postings) == 1
    assert postings[0]["doc_id"] == ir.doc_id


def test_index_error_result():
    _, indexer = _make_indexer()
    result = CrawlResult(url="https://bad.com", status_code=0, error="Timeout")
    ir = indexer.index_crawl_result(result)
    assert ir.indexed is False
    assert ir.error == "Timeout"


def test_index_sets_domain():
    store, indexer = _make_indexer()
    result = CrawlResult(
        url="https://docs.python.org/tutorial",
        status_code=200,
        title="Tutorial",
        body="Python tutorial content here",
    )
    ir = indexer.index_crawl_result(result)
    doc = store.get_document(ir.doc_id)
    assert doc.domain == "docs.python.org"


@pytest.mark.asyncio
async def test_crawl_and_index_single_page():
    store = Storage(":memory:")

    async def mock_fetch(url):
        if url == "https://example.com/":
            return CrawlResult(
                url="https://example.com/",
                status_code=200,
                title="Example",
                body="This is a test page about search engines",
                links=["https://example.com/about"],
            )
        return CrawlResult(url=url, status_code=0, error="Not mocked")

    crawler = MagicMock(spec=Crawler)
    crawler.fetch = AsyncMock(side_effect=mock_fetch)

    indexer = Indexer(storage=store, crawler=crawler)
    report = await indexer.crawl_and_index(
        "https://example.com/", max_pages=1, max_depth=0
    )

    assert report.pages_crawled == 1
    assert store.document_count() == 1


@pytest.mark.asyncio
async def test_crawl_follows_links_within_depth():
    store = Storage(":memory:")

    pages = {
        "https://site.com/": CrawlResult(
            url="https://site.com/",
            status_code=200,
            title="Home",
            body="Home page content",
            links=["https://site.com/page1", "https://site.com/page2"],
        ),
        "https://site.com/page1": CrawlResult(
            url="https://site.com/page1",
            status_code=200,
            title="Page 1",
            body="Page 1 content",
            links=[],
        ),
        "https://site.com/page2": CrawlResult(
            url="https://site.com/page2",
            status_code=200,
            title="Page 2",
            body="Page 2 content",
            links=[],
        ),
    }

    crawler = MagicMock(spec=Crawler)
    crawler.fetch = AsyncMock(
        side_effect=lambda url: pages.get(url, CrawlResult(url=url, status_code=404, error="not found"))
    )

    indexer = Indexer(storage=store, crawler=crawler)
    report = await indexer.crawl_and_index(
        "https://site.com/", max_pages=10, max_depth=1
    )

    assert report.pages_crawled == 3
    assert store.document_count() == 3


@pytest.mark.asyncio
async def test_crawl_respects_same_domain_only():
    store = Storage(":memory:")

    crawler = MagicMock(spec=Crawler)
    crawler.fetch = AsyncMock(return_value=CrawlResult(
        url="https://mysite.com/",
        status_code=200,
        title="My Site",
        body="content",
        links=["https://external.com/other", "https://mysite.com/internal"],
    ))

    indexer = Indexer(storage=store, crawler=crawler)
    await indexer.crawl_and_index(
        "https://mysite.com/", max_pages=5, max_depth=1, same_domain_only=True
    )

    # external.com should not be enqueued
    assert not store.is_known_url("https://external.com/other")
    assert store.is_known_url("https://mysite.com/internal")
