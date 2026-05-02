import pytest
from ai_web_search.cache import SearchCache


def test_cache_miss():
    cache = SearchCache(maxsize=10, ttl=60)
    assert cache.get("ns", {"q": "python"}) is None


def test_cache_hit():
    cache = SearchCache(maxsize=10, ttl=60)
    value = {"results": [1, 2, 3]}
    cache.set("ns", {"q": "python"}, value)
    assert cache.get("ns", {"q": "python"}) == value


def test_cache_different_namespaces():
    cache = SearchCache(maxsize=10, ttl=60)
    cache.set("web", {"q": "test"}, "web_value")
    cache.set("news", {"q": "test"}, "news_value")
    assert cache.get("web", {"q": "test"}) == "web_value"
    assert cache.get("news", {"q": "test"}) == "news_value"


def test_cache_key_order_independent():
    cache = SearchCache(maxsize=10, ttl=60)
    cache.set("ns", {"a": 1, "b": 2}, "value")
    assert cache.get("ns", {"b": 2, "a": 1}) == "value"


def test_cache_size():
    cache = SearchCache(maxsize=10, ttl=60)
    assert cache.size == 0
    cache.set("ns", {"q": "x"}, "v")
    assert cache.size == 1


def test_cache_clear():
    cache = SearchCache(maxsize=10, ttl=60)
    cache.set("ns", {"q": "x"}, "v")
    cache.clear()
    assert cache.size == 0
    assert cache.get("ns", {"q": "x"}) is None
