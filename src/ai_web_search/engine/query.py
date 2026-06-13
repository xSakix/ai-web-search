"""Query processor: parse query → retrieve candidates → rank with BM25 → build snippets."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from .bm25 import BM25, ScoredDoc
from .storage import Document, Storage
from .tokenizer import tokenize

PHRASE_RE = re.compile(r'"([^"]*)"')

_WINDOW = 30  # words each side of a match for snippet generation


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


def _build_snippet(body: str, query_terms: list[str], max_chars: int = 200) -> str:
    """Extract a snippet from the word-window richest in query terms (O(n) sliding window)."""
    if not body:
        return ""

    words = body.split()
    n = len(words)
    if n == 0:
        return ""

    term_set = set(query_terms)
    window = _WINDOW * 2

    # 1 if any query term is a substring of this word, else 0
    hits = [int(any(t in w.lower() for t in term_set)) for w in words]

    # Initialise first window
    win_sum = sum(hits[:window])
    best_sum, best_start = win_sum, 0

    # Slide across remaining positions
    for i in range(1, max(1, n - window + 1)):
        win_sum += hits[min(i + window - 1, n - 1)] - hits[i - 1]
        if win_sum > best_sum:
            best_sum, best_start = win_sum, i

    start = max(0, best_start - 5)
    end = min(n, best_start + window)
    snippet = " ".join(words[start:end])

    if start > 0:
        snippet = "…" + snippet
    if end < n:
        snippet = snippet + "…"

    if len(snippet) > max_chars:
        truncated = snippet[:max_chars].rsplit(" ", 1)[0]
        if not truncated.endswith("…"):
            truncated += "…"
        snippet = truncated
    return snippet


def _parse_query(raw_query: str) -> tuple[list[list[str]], list[str]]:
    """Split raw_query into phrase token-lists and free tokens."""
    phrases: list[list[str]] = []
    remainder = raw_query
    for m in PHRASE_RE.finditer(raw_query):
        phrase_tokens = tokenize(m.group(1))
        if phrase_tokens:
            phrases.append(phrase_tokens)
        remainder = remainder.replace(m.group(0), " ", 1)
    free_tokens = tokenize(remainder)
    return phrases, free_tokens


def _doc_contains_phrase(
    phrase_tokens: list[str], postings_map: dict[str, list[int]]
) -> bool:
    """Return True if phrase_tokens appear consecutively in postings_map."""
    if not all(t in postings_map for t in phrase_tokens):
        return False
    position_sets = {t: set(postings_map[t]) for t in phrase_tokens}
    for anchor in sorted(position_sets[phrase_tokens[0]]):
        if all(
            (anchor + i) in position_sets[tok]
            for i, tok in enumerate(phrase_tokens[1:], 1)
        ):
            return True
    return False


class QueryProcessor:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    def search(
        self, raw_query: str, top_k: int = 10, domain: str | None = None, offset: int = 0
    ) -> SearchResults:
        t0 = time.perf_counter()
        phrases, free_tokens = _parse_query(raw_query)
        all_tokens = free_tokens + [t for ph in phrases for t in ph]

        if not all_tokens:
            return SearchResults(
                query=raw_query, hits=[], total_docs=self._storage.document_count()
            )

        num_docs = self._storage.document_count()
        avg_len = self._storage.avg_word_count()
        bm25 = BM25(num_docs=max(num_docs, 1), avg_doc_len=max(avg_len, 1))

        # Domain pre-filter
        if domain is not None:
            allowed = self._storage.get_doc_ids_for_domain(domain)
            if not allowed:
                elapsed = (time.perf_counter() - t0) * 1000
                return SearchResults(
                    query=raw_query,
                    hits=[],
                    total_docs=num_docs,
                    elapsed_ms=round(elapsed, 1),
                )
        else:
            allowed = None

        # Gather per-term postings, building both scoring and position structures
        doc_terms: dict[int, list[tuple[str, int, int]]] = {}
        doc_positions: dict[int, dict[str, list[int]]] = {}
        for term in set(all_tokens):
            postings = self._storage.get_postings(term)
            df = len(postings)
            for posting in postings:
                doc_id = posting["doc_id"]
                if allowed is not None and doc_id not in allowed:
                    continue
                tf = posting["frequency"]
                doc_terms.setdefault(doc_id, []).append((term, tf, df))
                doc_positions.setdefault(doc_id, {})[term] = posting["positions"]

        if not doc_terms:
            elapsed = (time.perf_counter() - t0) * 1000
            return SearchResults(
                query=raw_query,
                hits=[],
                total_docs=num_docs,
                elapsed_ms=round(elapsed, 1),
            )

        # Score all candidate documents
        _docs: dict[int, Document] = {}
        scored: list[ScoredDoc] = []
        for doc_id, term_postings in doc_terms.items():
            doc = self._storage.get_document(doc_id)
            if doc is None:
                continue
            _docs[doc_id] = doc
            scored.append(bm25.score(doc_id, doc.word_count or 1, term_postings))

        # Title boost: free-token hits in the title get a 2× multiplier
        query_token_set = set(free_tokens)
        if query_token_set:
            for sd in scored:
                doc = _docs.get(sd.doc_id)
                if doc and set(tokenize(doc.title)) & query_token_set:
                    sd.score *= 2.0

        scored.sort(key=lambda s: s.score, reverse=True)

        # Phrase filter: remove docs where any required phrase is absent
        if phrases:
            scored = [
                sd
                for sd in scored
                if all(
                    _doc_contains_phrase(ph, doc_positions.get(sd.doc_id, {}))
                    for ph in phrases
                )
            ]

        top = scored[offset : offset + top_k]

        # Build hit objects from the cached _docs map
        hits: list[SearchHit] = []
        for sd in top:
            doc = _docs.get(sd.doc_id)
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
