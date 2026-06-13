from __future__ import annotations

from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Search index
    index_db_path: Path = Path("search_index.db")

    # Crawler
    crawl_delay_seconds: float = 1.0
    max_body_chars: int = 50_000

    # HTTP
    http_timeout_seconds: float = 15.0

    # Fetcher (for peek_document truncation)
    fetch_max_chars: int = 8_000

    # Authentication — required as Bearer token on HTTP transports when set
    api_key: SecretStr | None = None

    @field_validator("index_db_path", mode="after")
    @classmethod
    def _resolve_db_path(cls, v: Path) -> Path:
        return v.resolve()


settings = Settings()
