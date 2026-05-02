from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Provider API keys
    brave_api_key: str = ""
    serpapi_key: str = ""

    # Provider order (comma-separated)
    search_providers: str = "duckduckgo,brave"

    # Cache
    cache_ttl_seconds: int = 300
    cache_max_size: int = 512

    # HTTP
    http_timeout_seconds: float = 15.0
    http_max_retries: int = 2

    # Fetcher
    fetch_max_chars: int = 8000

    @property
    def provider_order(self) -> list[str]:
        return [p.strip() for p in self.search_providers.split(",") if p.strip()]


settings = Settings()
