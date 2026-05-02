from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Optional

from cachetools import TTLCache


class SearchCache:
    """Thread-safe TTL + LRU cache keyed by a hash of the search parameters."""

    def __init__(self, maxsize: int = 512, ttl: int = 300) -> None:
        self._cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)

    @staticmethod
    def _key(namespace: str, params: dict[str, Any]) -> str:
        raw = json.dumps({"ns": namespace, **params}, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, namespace: str, params: dict[str, Any]) -> Optional[Any]:
        return self._cache.get(self._key(namespace, params))

    def set(self, namespace: str, params: dict[str, Any], value: Any) -> None:
        self._cache[self._key(namespace, params)] = value

    @property
    def size(self) -> int:
        return len(self._cache)

    def clear(self) -> None:
        self._cache.clear()
