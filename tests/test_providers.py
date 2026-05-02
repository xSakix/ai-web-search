"""Provider unit tests – DuckDuckGo calls are mocked to avoid network I/O."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ai_web_search.models import SafeSearch, TimeRange
from ai_web_search.providers.duckduckgo import DuckDuckGoProvider
from ai_web_search.providers.registry import ProviderRegistry


@pytest.fixture
def ddg():
    return DuckDuckGoProvider()


def _mock_ddgs(text_results=None, news_results=None, image_results=None):
    """Build a context-manager mock for ddgs.DDGS."""
    instance = MagicMock()
    instance.__enter__ = MagicMock(return_value=instance)
    instance.__exit__ = MagicMock(return_value=False)
    if text_results is not None:
        instance.text.return_value = text_results
    if news_results is not None:
        instance.news.return_value = news_results
    if image_results is not None:
        instance.images.return_value = image_results
    return instance


def test_ddg_always_available(ddg):
    assert ddg.is_available() is True


@pytest.mark.asyncio
async def test_ddg_search_maps_fields(ddg):
    fake_results = [
        {"title": "Python", "href": "https://python.org", "body": "Official site"},
    ]
    with patch("ai_web_search.providers.duckduckgo.DDGS") as MockDDGS:
        MockDDGS.return_value = _mock_ddgs(text_results=fake_results)

        results = await ddg.search("python", num_results=1)

    assert len(results) == 1
    assert results[0].title == "Python"
    assert results[0].url == "https://python.org"
    assert results[0].snippet == "Official site"
    assert results[0].source == "python.org"


@pytest.mark.asyncio
async def test_ddg_search_passes_backend_arg(ddg):
    """Ensure backend='duckduckgo' is forwarded to ddgs to avoid Bing fallback."""
    fake_results = [{"title": "T", "href": "https://x.com", "body": "S"}]
    with patch("ai_web_search.providers.duckduckgo.DDGS") as MockDDGS:
        mock_instance = _mock_ddgs(text_results=fake_results)
        MockDDGS.return_value = mock_instance

        await ddg.search("test")

    call_kwargs = mock_instance.text.call_args.kwargs
    assert call_kwargs.get("backend") == "duckduckgo"


@pytest.mark.asyncio
async def test_ddg_search_empty_response(ddg):
    with patch("ai_web_search.providers.duckduckgo.DDGS") as MockDDGS:
        MockDDGS.return_value = _mock_ddgs(text_results=None)

        results = await ddg.search("no results query")

    assert results == []


@pytest.mark.asyncio
async def test_ddg_search_raises_on_rate_limit(ddg):
    from ddgs.exceptions import RatelimitException

    with patch("ai_web_search.providers.duckduckgo.DDGS") as MockDDGS:
        instance = _mock_ddgs()
        instance.text.side_effect = RatelimitException("rate limited")
        MockDDGS.return_value = instance

        with pytest.raises(RuntimeError, match="rate limit"):
            await ddg.search("test")


@pytest.mark.asyncio
async def test_ddg_news_maps_fields(ddg):
    fake = [
        {
            "title": "News headline",
            "url": "https://news.example.com/article",
            "body": "Summary",
            "date": "2024-01-01",
            "source": "Example News",
        }
    ]
    with patch("ai_web_search.providers.duckduckgo.DDGS") as MockDDGS:
        MockDDGS.return_value = _mock_ddgs(news_results=fake)

        results = await ddg.search_news("tech news", time_range=TimeRange.week)

    assert results[0].title == "News headline"
    assert results[0].published_date == "2024-01-01"
    assert results[0].source == "Example News"


@pytest.mark.asyncio
async def test_ddg_images_maps_fields(ddg):
    fake = [
        {
            "title": "Cool image",
            "url": "https://site.com/page",
            "image": "https://site.com/img.jpg",
            "width": 1920,
            "height": 1080,
        }
    ]
    with patch("ai_web_search.providers.duckduckgo.DDGS") as MockDDGS:
        MockDDGS.return_value = _mock_ddgs(image_results=fake)

        results = await ddg.search_images("landscape photo")

    assert results[0].title == "Cool image"
    assert results[0].image_url == "https://site.com/img.jpg"
    assert results[0].width == 1920


def test_registry_always_has_duckduckgo():
    registry = ProviderRegistry()
    assert "duckduckgo" in registry.available


def test_registry_primary_is_first_available():
    registry = ProviderRegistry()
    assert registry.primary is not None


def test_registry_get_known_provider():
    registry = ProviderRegistry()
    p = registry.get("duckduckgo")
    assert p is not None
    assert p.name == "duckduckgo"


def test_registry_get_unknown_provider():
    registry = ProviderRegistry()
    assert registry.get("nonexistent") is None
