import time

import pytest

from ai_web_search.engine.storage import Document, Storage


@pytest.fixture
def store():
    return Storage(":memory:")


def test_upsert_and_get_document(store):
    doc = Document(url="https://example.com", title="Example", body="Hello world", word_count=2)
    doc_id = store.upsert_document(doc)
    assert doc_id > 0

    retrieved = store.get_document(doc_id)
    assert retrieved is not None
    assert retrieved.url == "https://example.com"
    assert retrieved.title == "Example"


def test_upsert_is_idempotent(store):
    doc = Document(url="https://example.com", title="v1", body="first")
    id1 = store.upsert_document(doc)

    doc2 = Document(url="https://example.com", title="v2", body="second")
    id2 = store.upsert_document(doc2)

    # Same URL → same id, updated content
    assert id1 == id2
    retrieved = store.get_document(id1)
    assert retrieved.title == "v2"


def test_document_count(store):
    assert store.document_count() == 0
    store.upsert_document(Document(url="https://a.com", title="A", body="a"))
    store.upsert_document(Document(url="https://b.com", title="B", body="b"))
    assert store.document_count() == 2


def test_postings_roundtrip(store):
    doc_id = store.upsert_document(Document(url="https://x.com", title="X", body="test"))
    store.upsert_postings(doc_id, {"python": (3, [0, 5, 10]), "search": (1, [2])})

    postings = store.get_postings("python")
    assert len(postings) == 1
    assert postings[0]["doc_id"] == doc_id
    assert postings[0]["frequency"] == 3
    assert postings[0]["positions"] == [0, 5, 10]


def test_get_doc_freq(store):
    id1 = store.upsert_document(Document(url="https://a.com", title="A", body="a"))
    id2 = store.upsert_document(Document(url="https://b.com", title="B", body="b"))
    store.upsert_postings(id1, {"python": (1, [0])})
    store.upsert_postings(id2, {"python": (2, [0, 1])})

    assert store.get_doc_freq("python") == 2
    assert store.get_doc_freq("java") == 0


def test_postings_overwrite_on_reindex(store):
    doc_id = store.upsert_document(Document(url="https://x.com", title="X", body="test"))
    store.upsert_postings(doc_id, {"old_term": (1, [0])})
    store.upsert_postings(doc_id, {"new_term": (1, [0])})  # reindex

    assert store.get_postings("old_term") == []
    assert len(store.get_postings("new_term")) == 1


def test_crawl_queue_enqueue_dequeue(store):
    added = store.enqueue("https://a.com", depth=0, added_at="now")
    assert added is True

    item = store.dequeue()
    assert item is not None
    assert item["url"] == "https://a.com"
    assert item["depth"] == 0


def test_crawl_queue_no_duplicates(store):
    store.enqueue("https://a.com")
    added_again = store.enqueue("https://a.com")
    assert added_again is False


def test_mark_crawled(store):
    store.enqueue("https://a.com")
    store.dequeue()
    store.mark_crawled("https://a.com")
    stats = store.queue_stats()
    assert stats.get("crawled") == 1


def test_is_known_url(store):
    assert not store.is_known_url("https://new.com")
    store.enqueue("https://new.com")
    assert store.is_known_url("https://new.com")


def test_avg_word_count(store):
    store.upsert_document(Document(url="https://a.com", title="", body="", word_count=10))
    store.upsert_document(Document(url="https://b.com", title="", body="", word_count=20))
    assert store.avg_word_count() == 15.0


def test_domain_stats(store):
    store.upsert_document(Document(url="https://example.com/1", title="", body="", domain="example.com"))
    store.upsert_document(Document(url="https://example.com/2", title="", body="", domain="example.com"))
    store.upsert_document(Document(url="https://other.com/1", title="", body="", domain="other.com"))
    stats = store.domain_stats()
    assert stats[0]["domain"] == "example.com"
    assert stats[0]["n"] == 2


def test_prune_queue(store):
    store.enqueue("https://a.com", added_at="t1")
    store.enqueue("https://b.com", added_at="t2")
    store.enqueue("https://c.com", added_at="t3")
    store.mark_crawled("https://b.com")
    store.mark_failed("https://c.com")
    deleted = store.prune_queue()
    assert deleted == 2
    stats = store.queue_stats()
    assert stats.get("pending", 0) == 1
    assert "crawled" not in stats
    assert "failed" not in stats


def test_stats_cache_invalidated_by_upsert(store):
    store.upsert_document(Document(url="https://a.com", title="A", body="test", word_count=1))
    assert store.document_count() == 1
    # Freeze the cache timestamp so the next call would normally hit the cache
    store._stats_ts = time.monotonic()
    # upsert_document must reset _stats_ts to 0 so the next count is fresh
    store.upsert_document(Document(url="https://b.com", title="B", body="test", word_count=1))
    assert store.document_count() == 2
