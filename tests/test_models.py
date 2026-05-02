import pytest
from ai_web_search.models import (
    FetchedPage,
    ImageResult,
    SafeSearch,
    SearchResponse,
    SearchResult,
    TimeRange,
)


def test_search_result_minimal():
    r = SearchResult(title="T", url="https://example.com", snippet="S")
    assert r.title == "T"
    assert r.published_date is None


def test_search_response_serialises():
    resp = SearchResponse(
        query="python",
        provider="duckduckgo",
        results=[
            SearchResult(title="T", url="https://example.com", snippet="S")
        ],
    )
    d = resp.model_dump()
    assert d["query"] == "python"
    assert len(d["results"]) == 1
    assert d["cached"] is False


def test_fetched_page_defaults():
    page = FetchedPage(url="https://example.com", text="hello world")
    assert page.links == []
    assert page.status_code == 200
    assert page.fetched_at  # auto-populated


def test_safe_search_values():
    assert SafeSearch.off.value == "off"
    assert SafeSearch.moderate.value == "moderate"
    assert SafeSearch.strict.value == "strict"


def test_time_range_values():
    assert TimeRange.day.value == "day"
    assert TimeRange.week.value == "week"
