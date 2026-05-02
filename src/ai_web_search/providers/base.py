from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from ..models import ImageResult, SafeSearch, SearchResult, TimeRange


class SearchProvider(ABC):
    """Abstract base class for all search providers."""

    name: str = "base"

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this provider is configured and usable."""

    @abstractmethod
    async def search(
        self,
        query: str,
        num_results: int = 10,
        region: str = "wt-wt",
        safe_search: SafeSearch = SafeSearch.moderate,
    ) -> list[SearchResult]:
        """Run a web search and return a list of results."""

    @abstractmethod
    async def search_news(
        self,
        query: str,
        num_results: int = 10,
        time_range: Optional[TimeRange] = None,
        region: str = "wt-wt",
    ) -> list[SearchResult]:
        """Search news articles."""

    async def search_images(
        self,
        query: str,
        num_results: int = 10,
        region: str = "wt-wt",
        safe_search: SafeSearch = SafeSearch.moderate,
    ) -> list[ImageResult]:
        """Search images. Providers that don't support this return an empty list."""
        return []
