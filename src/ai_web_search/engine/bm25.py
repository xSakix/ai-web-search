"""BM25 (Okapi BM25) ranking function.

BM25 is the standard probabilistic retrieval model used in Elasticsearch,
Lucene, and most production search engines. It ranks documents by computing:

    score(D, Q) = Σ_i  IDF(q_i) · (f(q_i,D) · (k1+1))
                                   ─────────────────────────────────────────
                                   f(q_i,D) + k1·(1 - b + b·|D|/avgdl)

Where:
    f(q_i, D)  = term frequency of query term q_i in document D
    |D|        = document length (word count)
    avgdl      = average document length across corpus
    k1         = 1.5  (term-frequency saturation parameter)
    b          = 0.75 (document-length normalisation parameter)
    IDF(q_i)   = log((N - n(q_i) + 0.5) / (n(q_i) + 0.5) + 1)
    N          = total number of documents
    n(q_i)     = number of documents containing q_i
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class ScoredDoc:
    doc_id: int
    score: float
    term_hits: list[str] = field(default_factory=list)


class BM25:
    k1: float = 1.5
    b: float = 0.75

    def __init__(self, num_docs: int, avg_doc_len: float) -> None:
        self._n = num_docs
        self._avgdl = avg_doc_len if avg_doc_len > 0 else 1.0

    def idf(self, doc_freq: int) -> float:
        n, df = self._n, doc_freq
        return math.log((n - df + 0.5) / (df + 0.5) + 1)

    def term_score(self, tf: int, doc_len: int, doc_freq: int) -> float:
        idf = self.idf(doc_freq)
        k1, b, avgdl = self.k1, self.b, self._avgdl
        numerator = tf * (k1 + 1)
        denominator = tf + k1 * (1 - b + b * doc_len / avgdl)
        return idf * numerator / denominator

    def score(
        self,
        doc_id: int,
        doc_len: int,
        term_postings: list[tuple[str, int, int]],
    ) -> ScoredDoc:
        """
        term_postings: list of (term, tf_in_doc, df_in_corpus)
        Returns a ScoredDoc with the aggregate BM25 score.
        """
        total = 0.0
        hits: list[str] = []
        for term, tf, df in term_postings:
            if tf > 0:
                total += self.term_score(tf, doc_len, df)
                hits.append(term)
        return ScoredDoc(doc_id=doc_id, score=total, term_hits=hits)
