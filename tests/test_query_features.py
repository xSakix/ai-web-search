"""Tests for query-time features: phrase search, domain filter, title boosting."""

from __future__ import annotations

from urllib.parse import urlparse

from ai_web_search.engine.query import QueryProcessor, _doc_contains_phrase, _parse_query
from ai_web_search.engine.storage import Document, Storage
from ai_web_search.engine.tokenizer import tokenize_with_positions


def _make_store(*docs: dict) -> tuple[Storage, QueryProcessor]:
    """Create an in-memory index containing the given documents."""
    store = Storage(":memory:")
    for d in docs:
        title = d.get("title", "")
        description = d.get("description", "")
        body = d.get("body", "")
        domain = d.get("domain") or urlparse(d["url"]).netloc
        text = f"{title} {description} {body}"
        term_freqs = tokenize_with_positions(text)
        doc = Document(
            url=d["url"],
            title=title,
            body=body,
            description=description,
            domain=domain,
            word_count=len(text.split()),
        )
        doc_id = store.upsert_document(doc)
        store.upsert_postings(doc_id, term_freqs)
    return store, QueryProcessor(store)


# ── Unit tests for helper functions ───────────────────────────────────────────

def test_parse_query_extracts_phrase_and_free():
    phrases, free = _parse_query('python "machine learning" tutorial')
    assert phrases == [["machine", "learning"]]
    assert "python" in free and "tutorial" in free


def test_parse_query_no_phrases():
    phrases, free = _parse_query("python tutorial")
    assert phrases == []
    assert "python" in free and "tutorial" in free


def test_doc_contains_phrase_adjacent():
    assert _doc_contains_phrase(["machine", "learning"], {"machine": [3], "learning": [4]})


def test_doc_contains_phrase_non_adjacent():
    assert not _doc_contains_phrase(["machine", "learning"], {"machine": [3], "learning": [6]})


def test_doc_contains_phrase_missing_token():
    assert not _doc_contains_phrase(["machine", "learning"], {"machine": [3]})


def test_doc_contains_phrase_single_token():
    assert _doc_contains_phrase(["python"], {"python": [1, 5]})


# ── Phrase search (integration) ────────────────────────────────────────────────

def test_phrase_exact_match():
    _, qp = _make_store({"url": "https://a.com", "body": "machine learning guide"})
    results = qp.search('"machine learning"')
    assert len(results.hits) == 1
    assert results.hits[0].url == "https://a.com"


def test_phrase_non_adjacent_excluded():
    # "machine" and "learning" present but separated by a non-stopword
    _, qp = _make_store({"url": "https://a.com", "body": "machine algorithm for learning"})
    results = qp.search('"machine learning"')
    assert results.hits == []


def test_phrase_one_token_missing():
    _, qp = _make_store({"url": "https://a.com", "body": "machine learning guide"})
    results = qp.search('"machine neural"')
    assert results.hits == []


def test_mixed_phrase_and_free():
    # Free tokens affect ranking (not filtering), so both phrase-matching docs appear.
    # The doc that also contains the free token "python" ranks higher.
    _, qp = _make_store(
        {"url": "https://a.com", "body": "machine learning guide python"},
        {"url": "https://b.com", "body": "machine learning guide javascript"},
    )
    results = qp.search('"machine learning" python')
    assert len(results.hits) == 2
    assert results.hits[0].url == "https://a.com"


def test_phrase_stopwords_ignored():
    # "the" is a stopword; phrase collapses to single token ["python"]
    _, qp = _make_store({"url": "https://a.com", "body": "python programming language"})
    results = qp.search('"the python"')
    assert len(results.hits) == 1


def test_phrase_all_stopwords_returns_empty():
    _, qp = _make_store({"url": "https://a.com", "body": "python programming language"})
    results = qp.search('"the and or"')
    assert results.hits == []


def test_non_phrase_query_unaffected():
    _, qp = _make_store({"url": "https://a.com", "body": "machine learning"})
    results = qp.search("machine learning")
    assert len(results.hits) == 1


# ── Domain filter ──────────────────────────────────────────────────────────────

def test_domain_filter_restricts_to_domain():
    _, qp = _make_store(
        {"url": "https://python.org/guide", "body": "python tutorial", "domain": "python.org"},
        {"url": "https://rust-lang.org/guide", "body": "rust tutorial", "domain": "rust-lang.org"},
    )
    results = qp.search("tutorial", domain="python.org")
    assert len(results.hits) == 1
    assert results.hits[0].domain == "python.org"


def test_domain_filter_unknown_returns_empty():
    _, qp = _make_store({"url": "https://python.org/guide", "body": "python tutorial"})
    results = qp.search("tutorial", domain="unknown.com")
    assert results.hits == []


def test_no_domain_filter_returns_all():
    _, qp = _make_store(
        {"url": "https://python.org/guide", "body": "tutorial python"},
        {"url": "https://rust-lang.org/guide", "body": "tutorial rust"},
    )
    results = qp.search("tutorial")
    assert len(results.hits) == 2


def test_domain_filter_exact_no_subdomain_bleed():
    _, qp = _make_store(
        {"url": "https://python.org/guide", "body": "python tutorial", "domain": "python.org"},
        {"url": "https://docs.python.org/ref", "body": "docs tutorial", "domain": "docs.python.org"},
    )
    results = qp.search("tutorial", domain="python.org")
    assert len(results.hits) == 1
    assert results.hits[0].domain == "python.org"


# ── Title boosting ─────────────────────────────────────────────────────────────

def test_title_boost_elevates_title_match():
    _, qp = _make_store(
        {"url": "https://a.com", "title": "Python Tutorial", "body": "programming guide"},
        {"url": "https://b.com", "title": "Programming Tutorial", "body": "python guide"},
    )
    results = qp.search("python")
    assert results.hits[0].url == "https://a.com"


def test_title_boost_score_is_higher():
    _, qp = _make_store(
        {"url": "https://a.com", "title": "Python Tutorial", "body": "programming guide"},
        {"url": "https://b.com", "title": "Programming Tutorial", "body": "python guide"},
    )
    results = qp.search("python")
    assert results.hits[0].score > results.hits[1].score


def test_title_boost_not_applied_for_phrase_only_query():
    # Both docs contain "machine learning" adjacently; neither gets title boost
    # because free_tokens is empty for a phrase-only query.
    _, qp = _make_store(
        {"url": "https://a.com", "title": "Machine Learning", "body": "deep neural guide"},
        {"url": "https://b.com", "title": "Deep Neural", "body": "machine learning guide"},
    )
    results = qp.search('"machine learning"')
    assert len(results.hits) == 2
    assert results.hits[0].score == results.hits[1].score


def test_title_boost_partial_overlap_sufficient():
    # "python" from free tokens overlaps with doc1's title — boost applies
    _, qp = _make_store(
        {"url": "https://a.com", "title": "Python", "body": "tutorial guide content"},
        {"url": "https://b.com", "title": "Content Article", "body": "python tutorial guide"},
    )
    results = qp.search("python tutorial guide")
    assert results.hits[0].url == "https://a.com"


# ── Combined ───────────────────────────────────────────────────────────────────

def test_all_three_combined():
    # Only doc1 satisfies phrase ("machine learning") + domain (python.org)
    _, qp = _make_store(
        {
            "url": "https://python.org/ml",
            "title": "Machine Learning",
            "body": "machine learning guide python",
            "domain": "python.org",
        },
        {
            "url": "https://java.org/ml",
            "title": "Guide",
            "body": "machine learning tutorial java",
            "domain": "java.org",
        },
        {
            "url": "https://python.org/other",
            "title": "Other Content",
            "body": "python programming",
            "domain": "python.org",
        },
    )
    results = qp.search('"machine learning" python', domain="python.org")
    assert len(results.hits) == 1
    assert results.hits[0].url == "https://python.org/ml"
