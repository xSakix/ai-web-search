"""Indexer: orchestrates crawl → parse → tokenize → store pipeline."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlparse

from .crawler import CrawlResult, Crawler
from .storage import Document, Storage
from .tokenizer import tokenize_with_positions

logger = logging.getLogger(__name__)


@dataclass
class IndexResult:
    url: str
    indexed: bool
    doc_id: int = 0
    word_count: int = 0
    links_found: int = 0
    error: str = ""


@dataclass
class CrawlReport:
    seed_url: str
    pages_crawled: int = 0
    pages_failed: int = 0
    pages_skipped: int = 0
    indexed_urls: list[str] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)


class Indexer:
    def __init__(self, storage: Storage, crawler: Crawler) -> None:
        self._storage = storage
        self._crawler = crawler

    def index_crawl_result(self, result: CrawlResult) -> IndexResult:
        """Process a CrawlResult and write the document + postings to storage."""
        if result.error:
            return IndexResult(url=result.url, indexed=False, error=result.error)

        domain = urlparse(result.url).netloc
        now = datetime.now(timezone.utc).isoformat()

        # Combine title + description + body for indexing but store body separately
        index_text = f"{result.title} {result.description} {result.body}"
        term_freqs = tokenize_with_positions(index_text)
        word_count = len(index_text.split())

        doc = Document(
            url=result.url,
            title=result.title,
            body=result.body,
            description=result.description,
            domain=domain,
            word_count=word_count,
            crawled_at=now,
        )

        doc_id = self._storage.upsert_document(doc)
        self._storage.upsert_postings(doc_id, term_freqs)

        logger.debug("Indexed %s (%d terms, %d words)", result.url, len(term_freqs), word_count)

        return IndexResult(
            url=result.url,
            indexed=True,
            doc_id=doc_id,
            word_count=word_count,
            links_found=len(result.links),
        )

    async def crawl_and_index(
        self,
        seed_url: str,
        max_pages: int = 50,
        max_depth: int = 2,
        same_domain_only: bool = True,
    ) -> CrawlReport:
        """Crawl starting from *seed_url* up to *max_pages* pages."""
        report = CrawlReport(seed_url=seed_url)
        seed_domain = urlparse(seed_url).netloc
        now = datetime.now(timezone.utc).isoformat()

        self._storage.enqueue(seed_url, depth=0, added_at=now)

        while report.pages_crawled + report.pages_failed < max_pages:
            item = self._storage.dequeue()
            if item is None:
                break

            url = item["url"]
            depth = item["depth"]

            # Skip if already in document store (previously crawled)
            if self._storage.get_document_by_url(url) is not None:
                self._storage.mark_crawled(url)
                report.pages_skipped += 1
                continue

            logger.info("Crawling [depth=%d] %s", depth, url)
            result = await self._crawler.fetch(url)

            if result.error:
                self._storage.mark_failed(url)
                report.pages_failed += 1
                report.errors.append({"url": url, "error": result.error})
                logger.warning("Failed %s: %s", url, result.error)
                continue

            index_result = self.index_crawl_result(result)
            if index_result.indexed:
                self._storage.mark_crawled(url)
                report.pages_crawled += 1
                report.indexed_urls.append(url)

                # Enqueue outbound links if within depth limit
                if depth < max_depth:
                    for link in result.links:
                        if same_domain_only and urlparse(link).netloc != seed_domain:
                            continue
                        if not self._storage.is_known_url(link):
                            self._storage.enqueue(
                                link, depth=depth + 1,
                                parent_url=url, added_at=now,
                            )
            else:
                self._storage.mark_failed(url)
                report.pages_failed += 1

        return report
