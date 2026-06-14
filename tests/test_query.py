"""Integration tests for the query processor using an in-memory index."""

import pytest

from ai_web_search.engine.indexer import Indexer
from ai_web_search.engine.crawler import CrawlResult
from ai_web_search.engine.query import QueryProcessor
from ai_web_search.engine.storage import Storage


def _build_index() -> tuple[Storage, QueryProcessor]:
    store = Storage(":memory:")
    # Manually index three documents
    docs = [
        CrawlResult(
            url="https://python.org",
            status_code=200,
            title="Python Programming Language",
            body="Python is a high-level general-purpose programming language. "
                 "It is known for its simple syntax and readability. "
                 "Python supports multiple programming paradigms.",
            description="Official Python website",
        ),
        CrawlResult(
            url="https://rust-lang.org",
            status_code=200,
            title="Rust Programming Language",
            body="Rust is a systems programming language focused on safety, speed, "
                 "and concurrency. Rust has no garbage collector.",
            description="Official Rust website",
        ),
        CrawlResult(
            url="https://example.com/cooking",
            status_code=200,
            title="Easy Pasta Recipes",
            body="Pasta is a type of Italian food made from dough. "
                 "Popular pasta recipes include spaghetti carbonara and lasagna.",
            description="Cooking tips",
        ),
    ]
    from ai_web_search.engine.tokenizer import tokenize_with_positions
    from ai_web_search.engine.storage import Document
    from urllib.parse import urlparse
    for cr in docs:
        domain = urlparse(cr.url).netloc
        text = f"{cr.title} {cr.description} {cr.body}"
        term_freqs = tokenize_with_positions(text)
        doc = Document(
            url=cr.url,
            title=cr.title,
            body=cr.body,
            description=cr.description,
            domain=domain,
            word_count=len(text.split()),
        )
        doc_id = store.upsert_document(doc)
        store.upsert_postings(doc_id, term_freqs)

    return store, QueryProcessor(store)


def test_search_returns_relevant_results():
    _, qp = _build_index()
    results = qp.search("python programming")
    assert len(results.hits) > 0
    assert results.hits[0].url == "https://python.org"


def test_irrelevant_query_returns_no_hits():
    _, qp = _build_index()
    results = qp.search("quantum entanglement blockchain nft")
    assert results.hits == []


def test_top_k_respected():
    _, qp = _build_index()
    results = qp.search("programming language", top_k=1)
    assert len(results.hits) <= 1


def test_snippet_contains_query_term():
    _, qp = _build_index()
    results = qp.search("pasta recipes")
    assert results.hits[0].url == "https://example.com/cooking"
    snippet = results.hits[0].snippet.lower()
    assert "pasta" in snippet


def test_scores_are_sorted_descending():
    _, qp = _build_index()
    results = qp.search("programming language")
    scores = [h.score for h in results.hits]
    assert scores == sorted(scores, reverse=True)


def test_total_docs_reported():
    store, qp = _build_index()
    results = qp.search("anything")
    assert results.total_docs == store.document_count()


def test_empty_query_returns_no_hits():
    _, qp = _build_index()
    results = qp.search("")
    assert results.hits == []


def test_stopword_only_query():
    _, qp = _build_index()
    results = qp.search("the and or but")
    assert results.hits == []


def test_search_pagination_offset():
    _, qp = _build_index()
    all_results = qp.search("programming language", top_k=2, offset=0)
    assert len(all_results.hits) >= 2
    page2 = qp.search("programming language", top_k=1, offset=1)
    assert len(page2.hits) == 1
    assert page2.hits[0].url == all_results.hits[1].url
