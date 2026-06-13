"""Query processor: parse query → retrieve candidates → rank with BM25 → build snippets."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from .bm25 import BM25, ScoredDoc
from .storage import Storage
from .tokenizer import tokenize


@dataclass
class SearchHit:
    url: str
    title: str
    snippet: str
    score: float
    domain: str = ""
    word_count: int = 0


@dataclass
class SearchResults:
    query: str
    hits: list[SearchHit]
    total_docs: int
    elapsed_ms: float = 0.0


_WINDOW = 30  # words each side of a match for snippet generation


def _build_snippet(body: str, query_terms: list[str], max_chars: int = 200) -> str:
    """Extract a sentence-aware snippet containing as many query terms as possible."""
    if not body:
        return ""

    lower_body = body.lower()
    best_start = 0
    best_hits = 0

    words = body.split()
    lower_words = lower_body.split()

    # Find the word-window with the most query-term hits
    for i in range(len(lower_words)):
        window = lower_words[i : i + _WINDOW * 2]
        hits = sum(1 for t in query_terms if any(t in w for w in window))
        if hits > best_hits:
            best_hits = hits
            best_start = i

    start = max(0, best_start - 5)
    end = min(len(words), best_start + _WINDOW * 2)
    snippet = " ".join(words[start:end])

    if start > 0:
        snippet = "…" + snippet
    if end < len(words):
        snippet = snippet + "…"

    if len(snippet) > max_chars:
        truncated = snippet[:max_chars].rsplit(" ", 1)[0]
        if not truncated.endswith("…"):
            truncated += "…"
        snippet = truncated
    return snippet


class QueryProcessor:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    def search(self, raw_query: str, top_k: int = 10) -> SearchResults:
        t0 = time.perf_counter()
        tokens = tokenize(raw_query)
        if not tokens:
            return SearchResults(query=raw_query, hits=[], total_docs=self._storage.document_count())

        num_docs = self._storage.document_count()
        avg_len = self._storage.avg_word_count()
        bm25 = BM25(num_docs=max(num_docs, 1), avg_doc_len=max(avg_len, 1))

        # Gather per-term postings and build doc→{term: (tf, df)} map
        doc_terms: dict[int, list[tuple[str, int, int]]] = {}
        for term in set(tokens):
            postings = self._storage.get_postings(term)
            df = len(postings)
            for posting in postings:
                doc_id = posting["doc_id"]
                tf = posting["frequency"]
                doc_terms.setdefault(doc_id, []).append((term, tf, df))

        if not doc_terms:
            elapsed = (time.perf_counter() - t0) * 1000
            return SearchResults(
                query=raw_query,
                hits=[],
                total_docs=num_docs,
                elapsed_ms=round(elapsed, 1),
            )

        # Score all candidate documents
        scored: list[ScoredDoc] = []
        for doc_id, term_postings in doc_terms.items():
            doc = self._storage.get_document(doc_id)
            if doc is None:
                continue
            scored.append(bm25.score(doc_id, doc.word_count or 1, term_postings))

        scored.sort(key=lambda s: s.score, reverse=True)
        top = scored[:top_k]

        # Build hit objects
        hits: list[SearchHit] = []
        for sd in top:
            doc = self._storage.get_document(sd.doc_id)
            if doc is None:
                continue
            snippet = _build_snippet(doc.body, sd.term_hits)
            hits.append(
                SearchHit(
                    url=doc.url,
                    title=doc.title or doc.url,
                    snippet=snippet or doc.description,
                    score=round(sd.score, 4),
                    domain=doc.domain,
                    word_count=doc.word_count,
                )
            )

        elapsed = (time.perf_counter() - t0) * 1000
        return SearchResults(
            query=raw_query,
            hits=hits,
            total_docs=num_docs,
            elapsed_ms=round(elapsed, 1),
        )
