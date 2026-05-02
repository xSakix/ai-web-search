"""Provider unit tests – DuckDuckGo calls are mocked to avoid network I/O."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_web_search.models import SafeSearch, SearchResult, TimeRange
from ai_web_search.providers.duckduckgo import DuckDuckGoProvider
from ai_web_search.providers.registry import ProviderRegistry


@pytest.fixture
def ddg():
    return DuckDuckGoProvider()


def test_ddg_always_available(ddg):
    assert ddg.is_available() is True


@pytest.mark.asyncio
async def test_ddg_search_maps_fields(ddg):
    fake_results = [
        {"title": "Python", "href": "https://python.org", "body": "Official site"},
    ]
    with patch("ai_web_search.providers.duckduckgo.DDGS") as MockDDGS:
        instance = MagicMock()
        instance.__enter__ = MagicMock(return_value=instance)
        instance.__exit__ = MagicMock(return_value=False)
        instance.text.return_value = fake_results
        MockDDGS.return_value = instance

        results = await ddg.search("python", num_results=1)

    assert len(results) == 1
    assert results[0].title == "Python"
    assert results[0].url == "https://python.org"
    assert results[0].snippet == "Official site"
    assert results[0].source == "python.org"


@pytest.mark.asyncio
async def test_ddg_search_empty_response(ddg):
    with patch("ai_web_search.providers.duckduckgo.DDGS") as MockDDGS:
        instance = MagicMock()
        instance.__enter__ = MagicMock(return_value=instance)
        instance.__exit__ = MagicMock(return_value=False)
        instance.text.return_value = None
        MockDDGS.return_value = instance

        results = await ddg.search("no results query")

    assert results == []


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
        instance = MagicMock()
        instance.__enter__ = MagicMock(return_value=instance)
        instance.__exit__ = MagicMock(return_value=False)
        instance.news.return_value = fake
        MockDDGS.return_value = instance

        results = await ddg.search_news("tech news", time_range=TimeRange.week)

    assert results[0].title == "News headline"
    assert results[0].published_date == "2024-01-01"


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
