"""Crawler tests using httpx mock transport — no real network calls."""

import httpx
import pytest

from ai_web_search.engine.crawler import Crawler, _extract_links, _extract_text, _is_crawlable
from bs4 import BeautifulSoup

SAMPLE_HTML = """
<html>
<head>
  <title>Test Page</title>
  <meta name="description" content="A test page for crawling">
</head>
<body>
  <nav>Navigation noise</nav>
  <main>
    <h1>Main Content</h1>
    <p>This paragraph has useful text about Python programming.</p>
    <a href="/page2">Internal link</a>
    <a href="https://external.com/page">External link</a>
    <a href="mailto:x@y.com">Email</a>
    <a href="https://example.com/image.jpg">JPEG image</a>
  </main>
  <script>var x = 1;</script>
  <footer>Footer noise</footer>
</body>
</html>
"""

ROBOTS_TXT = "User-agent: *\nDisallow: /private/\n"


def test_is_crawlable_http():
    assert _is_crawlable("https://example.com/page")
    assert _is_crawlable("http://example.com/page")


def test_is_crawlable_rejects_non_http():
    assert not _is_crawlable("ftp://example.com/file")
    assert not _is_crawlable("mailto:x@y.com")


def test_is_crawlable_rejects_binary_extensions():
    assert not _is_crawlable("https://example.com/file.pdf")
    assert not _is_crawlable("https://example.com/image.jpg")
    assert not _is_crawlable("https://example.com/script.js")


def test_extract_text_removes_noise():
    soup = BeautifulSoup(SAMPLE_HTML, "lxml")
    text = _extract_text(soup)
    assert "Main Content" in text
    assert "useful text" in text
    assert "var x = 1" not in text
    assert "Navigation noise" not in text


def test_extract_links_resolves_relative():
    soup = BeautifulSoup(SAMPLE_HTML, "lxml")
    links = _extract_links(soup, "https://example.com")
    assert "https://example.com/page2" in links


def test_extract_links_includes_external():
    soup = BeautifulSoup(SAMPLE_HTML, "lxml")
    links = _extract_links(soup, "https://example.com")
    assert "https://external.com/page" in links


def test_extract_links_skips_mailto():
    soup = BeautifulSoup(SAMPLE_HTML, "lxml")
    links = _extract_links(soup, "https://example.com")
    assert not any("mailto" in l for l in links)


def test_extract_links_skips_binary_files():
    soup = BeautifulSoup(SAMPLE_HTML, "lxml")
    links = _extract_links(soup, "https://example.com")
    assert not any(l.endswith(".jpg") for l in links)


def _make_transport(responses: dict[str, httpx.Response]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return responses.get(str(request.url), httpx.Response(404, text="Not found"))
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_crawler_fetches_html():
    transport = _make_transport({
        "https://example.com/robots.txt": httpx.Response(200, text=ROBOTS_TXT),
        "https://example.com/": httpx.Response(
            200, text=SAMPLE_HTML,
            headers={"content-type": "text/html; charset=utf-8"}
        ),
    })
    crawler = Crawler(crawl_delay=0)
    crawler._client = httpx.AsyncClient(transport=transport)

    result = await crawler.fetch("https://example.com/")

    assert result.error == ""
    assert result.title == "Test Page"
    assert result.description == "A test page for crawling"
    assert "Main Content" in result.body
    assert result.status_code == 200
    await crawler.aclose()


@pytest.mark.asyncio
async def test_crawler_respects_robots_txt():
    transport = _make_transport({
        "https://example.com/robots.txt": httpx.Response(
            200, text="User-agent: *\nDisallow: /\n"
        ),
        "https://example.com/page": httpx.Response(
            200, text=SAMPLE_HTML,
            headers={"content-type": "text/html"}
        ),
    })
    crawler = Crawler(crawl_delay=0)
    crawler._client = httpx.AsyncClient(transport=transport)

    result = await crawler.fetch("https://example.com/page")

    assert "robots.txt" in result.error
    await crawler.aclose()


@pytest.mark.asyncio
async def test_crawler_handles_http_error():
    transport = _make_transport({
        "https://example.com/robots.txt": httpx.Response(200, text=""),
        "https://example.com/missing": httpx.Response(
            404, text="Not found",
            headers={"content-type": "text/html"}
        ),
    })
    crawler = Crawler(crawl_delay=0)
    crawler._client = httpx.AsyncClient(transport=transport)

    result = await crawler.fetch("https://example.com/missing")

    assert result.status_code == 404
    assert result.error != ""
    await crawler.aclose()


@pytest.mark.asyncio
async def test_crawler_rejects_non_html():
    # Use a plain path (no blocked extension) so the content-type check runs
    transport = _make_transport({
        "https://example.com/robots.txt": httpx.Response(200, text=""),
        "https://example.com/api/results": httpx.Response(
            200, text='{"key": "val"}',
            headers={"content-type": "application/json"},
        ),
    })
    crawler = Crawler(crawl_delay=0)
    crawler._client = httpx.AsyncClient(transport=transport)

    result = await crawler.fetch("https://example.com/api/results")

    assert "Non-HTML" in result.error
    await crawler.aclose()


@pytest.mark.asyncio
async def test_crawler_rejects_post_redirect_blocked_extension():
    # Simulate a redirect from a clean URL to one with a blocked extension (.js).
    # The post-redirect SSRF guard must catch this even though the initial URL was clean.
    transport = _make_transport({
        "https://legit.com/robots.txt": httpx.Response(200, text=""),
        "https://legit.com/page": httpx.Response(
            301,
            headers={"location": "https://legit.com/bundle.js"},
            text="",
        ),
        "https://legit.com/bundle.js": httpx.Response(
            200, text="alert(1)",
            headers={"content-type": "text/html"},
        ),
    })
    crawler = Crawler(crawl_delay=0)
    crawler._client = httpx.AsyncClient(
        transport=transport, follow_redirects=True, max_redirects=5
    )

    result = await crawler.fetch("https://legit.com/page")

    assert "Post-redirect" in result.error
    await crawler.aclose()
