from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


class SafeSearch(str, Enum):
    off = "off"
    moderate = "moderate"
    strict = "strict"


class TimeRange(str, Enum):
    day = "day"
    week = "week"
    month = "month"
    year = "year"


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str
    published_date: Optional[str] = None
    source: Optional[str] = None  # domain name


class ImageResult(BaseModel):
    title: str
    url: str
    image_url: str
    width: Optional[int] = None
    height: Optional[int] = None
    source: Optional[str] = None


class SearchResponse(BaseModel):
    query: str
    provider: str
    results: list[SearchResult]
    total_results: Optional[int] = None
    cached: bool = False
    elapsed_ms: Optional[float] = None


class FetchedPage(BaseModel):
    url: str
    title: Optional[str] = None
    text: str
    links: list[str] = Field(default_factory=list)
    fetched_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    content_type: Optional[str] = None
    status_code: int = 200
