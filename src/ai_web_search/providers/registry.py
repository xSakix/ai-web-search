from __future__ import annotations

from .base import SearchProvider
from .brave import BraveProvider
from .duckduckgo import DuckDuckGoProvider

_ALL_PROVIDERS: dict[str, type[SearchProvider]] = {
    "duckduckgo": DuckDuckGoProvider,
    "brave": BraveProvider,
}

_DEFAULT_ORDER = ["duckduckgo", "brave"]


class ProviderRegistry:
    """Selects the first available provider according to configured priority."""

    def __init__(self, provider_order: list[str] | None = None) -> None:
        self._providers: list[SearchProvider] = []
        for name in (provider_order or _DEFAULT_ORDER):
            cls = _ALL_PROVIDERS.get(name)
            if cls is None:
                continue
            instance = cls()
            if instance.is_available():
                self._providers.append(instance)

        # Always ensure DuckDuckGo is available as the last resort
        names_loaded = {p.name for p in self._providers}
        if "duckduckgo" not in names_loaded:
            self._providers.append(DuckDuckGoProvider())

    @property
    def primary(self) -> SearchProvider:
        return self._providers[0]

    @property
    def available(self) -> list[str]:
        return [p.name for p in self._providers]

    def get(self, name: str) -> SearchProvider | None:
        for p in self._providers:
            if p.name == name:
                return p
        return None
