"""Fetcher tests using httpx mock transport."""

from __future__ import annotations

import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock

from ai_web_search.fetcher import PageFetcher, _clean_text, _extract_links
from bs4 import BeautifulSoup


SAMPLE_HTML = """
<html>
<head><title>Test Page</title></head>
<body>
  <nav>Navigation junk</nav>
  <main>
    <h1>Hello World</h1>
    <p>This is a test paragraph with useful content.</p>
    <a href="/relative">Relative link</a>
    <a href="https://external.com">External link</a>
  </main>
  <script>var x = 1;</script>
  <footer>Footer noise</footer>
</body>
</html>
"""


def test_clean_text_strips_script_and_nav():
    soup = BeautifulSoup(SAMPLE_HTML, "lxml")
    text = _clean_text(soup)
    assert "Hello World" in text
    assert "useful content" in text
    assert "var x = 1" not in text


def test_extract_links_resolves_relative():
    soup = BeautifulSoup(SAMPLE_HTML, "lxml")
    links = _extract_links(soup, "https://example.com")
    assert "https://example.com/relative" in links
    assert "https://external.com" in links


def test_extract_links_skips_mailto():
    html = '<a href="mailto:test@example.com">mail</a>'
    soup = BeautifulSoup(html, "lxml")
    links = _extract_links(soup, "https://example.com")
    assert links == []


@pytest.mark.asyncio
async def test_fetch_page_html():
    transport = httpx.MockTransport(
        lambda req: httpx.Response(
            200,
            content=SAMPLE_HTML.encode(),
            headers={"content-type": "text/html; charset=utf-8"},
        )
    )
    fetcher = PageFetcher()
    fetcher._client = httpx.AsyncClient(transport=transport)

    page = await fetcher.fetch("https://example.com", extract_links=True)

    assert page.title == "Test Page"
    assert "Hello World" in page.text
    assert page.status_code == 200
    assert len(page.links) > 0
    await fetcher.aclose()


@pytest.mark.asyncio
async def test_fetch_page_non_html():
    transport = httpx.MockTransport(
        lambda req: httpx.Response(
            200,
            content=b'{"key": "value"}',
            headers={"content-type": "application/json"},
        )
    )
    fetcher = PageFetcher()
    fetcher._client = httpx.AsyncClient(transport=transport)

    page = await fetcher.fetch("https://api.example.com/data")

    assert '{"key": "value"}' in page.text
    await fetcher.aclose()
