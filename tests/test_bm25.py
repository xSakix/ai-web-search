import math

import pytest

from ai_web_search.engine.bm25 import BM25, ScoredDoc


def test_idf_increases_with_lower_doc_freq():
    bm = BM25(num_docs=1000, avg_doc_len=100)
    idf_rare = bm.idf(doc_freq=1)
    idf_common = bm.idf(doc_freq=500)
    assert idf_rare > idf_common


def test_idf_never_negative():
    bm = BM25(num_docs=10, avg_doc_len=50)
    for df in range(1, 11):
        assert bm.idf(df) >= 0


def test_score_increases_with_term_freq():
    bm = BM25(num_docs=100, avg_doc_len=100)
    score_low = bm.term_score(tf=1, doc_len=100, doc_freq=5)
    score_high = bm.term_score(tf=5, doc_len=100, doc_freq=5)
    assert score_high > score_low


def test_score_penalises_long_docs():
    bm = BM25(num_docs=100, avg_doc_len=100)
    score_short = bm.term_score(tf=3, doc_len=50, doc_freq=5)
    score_long = bm.term_score(tf=3, doc_len=500, doc_freq=5)
    assert score_short > score_long


def test_score_aggregates_terms():
    bm = BM25(num_docs=100, avg_doc_len=100)
    sd = bm.score(
        doc_id=1,
        doc_len=100,
        term_postings=[("python", 3, 10), ("search", 1, 20)],
    )
    assert isinstance(sd, ScoredDoc)
    assert sd.doc_id == 1
    assert sd.score > 0
    assert set(sd.term_hits) == {"python", "search"}


def test_zero_tf_term_not_counted():
    bm = BM25(num_docs=100, avg_doc_len=100)
    sd_with = bm.score(1, 100, [("python", 2, 5)])
    sd_without = bm.score(1, 100, [("python", 0, 5)])
    assert sd_with.score > 0
    assert sd_without.score == 0
    assert "python" not in sd_without.term_hits
