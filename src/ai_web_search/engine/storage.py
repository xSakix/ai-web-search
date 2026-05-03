"""Storage layer: SQLite-backed document store and inverted index."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional


@dataclass
class Document:
    url: str
    title: str
    body: str
    description: str = ""
    domain: str = ""
    word_count: int = 0
    crawled_at: str = ""
    id: Optional[int] = None


@dataclass
class IndexEntry:
    term: str
    doc_id: int
    frequency: int
    positions: list[int] = field(default_factory=list)


_DDL = """
CREATE TABLE IF NOT EXISTS documents (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    url         TEXT    UNIQUE NOT NULL,
    title       TEXT    NOT NULL DEFAULT '',
    body        TEXT    NOT NULL DEFAULT '',
    description TEXT    NOT NULL DEFAULT '',
    domain      TEXT    NOT NULL DEFAULT '',
    word_count  INTEGER NOT NULL DEFAULT 0,
    crawled_at  TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS inverted_index (
    term      TEXT    NOT NULL,
    doc_id    INTEGER NOT NULL,
    frequency INTEGER NOT NULL DEFAULT 1,
    positions TEXT    NOT NULL DEFAULT '[]',
    PRIMARY KEY (term, doc_id),
    FOREIGN KEY (doc_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS crawl_queue (
    url        TEXT PRIMARY KEY,
    depth      INTEGER NOT NULL DEFAULT 0,
    status     TEXT    NOT NULL DEFAULT 'pending',
    parent_url TEXT,
    added_at   TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_inverted_term  ON inverted_index (term);
CREATE INDEX IF NOT EXISTS idx_inverted_docid ON inverted_index (doc_id);
CREATE INDEX IF NOT EXISTS idx_queue_status   ON crawl_queue (status);
CREATE INDEX IF NOT EXISTS idx_doc_domain     ON documents (domain);
"""


class Storage:
    """Thread-safe SQLite storage. Each thread gets its own connection."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._db_path = str(db_path)
        self._local = threading.local()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        if not getattr(self._local, "conn", None):
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return self._local.conn

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _init_schema(self) -> None:
        with self._tx() as conn:
            conn.executescript(_DDL)

    # ── Documents ─────────────────────────────────────────────────────────────

    def upsert_document(self, doc: Document) -> int:
        with self._tx() as conn:
            conn.execute(
                """
                INSERT INTO documents (url, title, body, description, domain, word_count, crawled_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    title      = excluded.title,
                    body       = excluded.body,
                    description= excluded.description,
                    domain     = excluded.domain,
                    word_count = excluded.word_count,
                    crawled_at = excluded.crawled_at
                """,
                (
                    doc.url, doc.title, doc.body, doc.description,
                    doc.domain, doc.word_count, doc.crawled_at,
                ),
            )
            # Always SELECT after upsert: SQLite's lastrowid may return the
            # speculative autoincrement value (not the existing id) on conflict.
            row = conn.execute("SELECT id FROM documents WHERE url=?", (doc.url,)).fetchone()
            return row["id"]

    def get_document(self, doc_id: int) -> Optional[Document]:
        row = self._connect().execute(
            "SELECT * FROM documents WHERE id=?", (doc_id,)
        ).fetchone()
        return _row_to_doc(row) if row else None

    def get_document_by_url(self, url: str) -> Optional[Document]:
        row = self._connect().execute(
            "SELECT * FROM documents WHERE url=?", (url,)
        ).fetchone()
        return _row_to_doc(row) if row else None

    def document_count(self) -> int:
        return self._connect().execute("SELECT COUNT(*) FROM documents").fetchone()[0]

    def avg_word_count(self) -> float:
        row = self._connect().execute("SELECT AVG(word_count) FROM documents").fetchone()
        return float(row[0] or 0)

    # ── Inverted index ────────────────────────────────────────────────────────

    def upsert_postings(self, doc_id: int, term_freqs: dict[str, tuple[int, list[int]]]) -> None:
        """Write term→(freq, positions) postings for a document."""
        with self._tx() as conn:
            conn.execute("DELETE FROM inverted_index WHERE doc_id=?", (doc_id,))
            conn.executemany(
                "INSERT INTO inverted_index (term, doc_id, frequency, positions) VALUES (?,?,?,?)",
                [
                    (term, doc_id, freq, json.dumps(positions))
                    for term, (freq, positions) in term_freqs.items()
                ],
            )

    def get_postings(self, term: str) -> list[dict]:
        """Return list of {doc_id, frequency, positions} for a term."""
        rows = self._connect().execute(
            "SELECT doc_id, frequency, positions FROM inverted_index WHERE term=?",
            (term,),
        ).fetchall()
        return [
            {"doc_id": r["doc_id"], "frequency": r["frequency"],
             "positions": json.loads(r["positions"])}
            for r in rows
        ]

    def get_doc_freq(self, term: str) -> int:
        """Number of documents containing term."""
        row = self._connect().execute(
            "SELECT COUNT(*) FROM inverted_index WHERE term=?", (term,)
        ).fetchone()
        return row[0]

    # ── Crawl queue ───────────────────────────────────────────────────────────

    def enqueue(self, url: str, depth: int = 0, parent_url: Optional[str] = None, added_at: str = "") -> bool:
        """Add URL to queue. Returns True if it was newly added."""
        try:
            with self._tx() as conn:
                conn.execute(
                    "INSERT INTO crawl_queue (url, depth, parent_url, added_at) VALUES (?,?,?,?)",
                    (url, depth, parent_url, added_at),
                )
            return True
        except sqlite3.IntegrityError:
            return False  # already queued

    def dequeue(self) -> Optional[dict]:
        """Pop the next pending URL from the queue."""
        with self._tx() as conn:
            row = conn.execute(
                "SELECT url, depth, parent_url FROM crawl_queue WHERE status='pending' ORDER BY depth, rowid LIMIT 1"
            ).fetchone()
            if not row:
                return None
            conn.execute(
                "UPDATE crawl_queue SET status='crawling' WHERE url=?", (row["url"],)
            )
        return dict(row)

    def mark_crawled(self, url: str) -> None:
        with self._tx() as conn:
            conn.execute("UPDATE crawl_queue SET status='crawled' WHERE url=?", (url,))

    def mark_failed(self, url: str) -> None:
        with self._tx() as conn:
            conn.execute("UPDATE crawl_queue SET status='failed' WHERE url=?", (url,))

    def queue_stats(self) -> dict[str, int]:
        rows = self._connect().execute(
            "SELECT status, COUNT(*) as n FROM crawl_queue GROUP BY status"
        ).fetchall()
        return {r["status"]: r["n"] for r in rows}

    def is_known_url(self, url: str) -> bool:
        row = self._connect().execute(
            "SELECT 1 FROM crawl_queue WHERE url=?", (url,)
        ).fetchone()
        return row is not None

    def domain_stats(self) -> list[dict]:
        rows = self._connect().execute(
            "SELECT domain, COUNT(*) as n FROM documents GROUP BY domain ORDER BY n DESC LIMIT 20"
        ).fetchall()
        return [dict(r) for r in rows]


def _row_to_doc(row: sqlite3.Row) -> Document:
    return Document(
        id=row["id"],
        url=row["url"],
        title=row["title"],
        body=row["body"],
        description=row["description"],
        domain=row["domain"],
        word_count=row["word_count"],
        crawled_at=row["crawled_at"],
    )
