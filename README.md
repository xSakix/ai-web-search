# AI Web Search – MCP Server

A self-hosted web search engine exposed as a [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server. It crawls web pages, builds a local full-text index, and answers queries using BM25 ranking — no third-party search API required.

## How it works

```
crawl_url
    │
    ▼
Crawler (httpx + robots.txt)
    │  fetches pages, follows links
    ▼
Indexer
    │  tokenize → BM25 inverted index
    ▼
SQLite (search_index.db)
    ├── documents        – crawled page text
    ├── inverted_index   – term → (doc_id, freq, positions)
    └── crawl_queue      – BFS frontier with status tracking
    │
    ▼
QueryProcessor  ──→  search
    BM25 ranking + context-aware snippets
```

## Quick Start

```bash
# 1. Install
pip install -e .

# 2. Run
ai-web-search
```

The server stores its index in `search_index.db` in the current directory (configurable via `INDEX_DB_PATH`).

## MCP Tools

| Tool | Description |
|------|-------------|
| `crawl_url(url, max_pages?, max_depth?, same_domain_only?)` | Crawl a URL and add pages to the index |
| `search(query, top_k?)` | BM25 search over the local index |
| `get_stats()` | Index and crawl-queue statistics |
| `list_domains(limit?)` | Domain distribution in the index |
| `peek_document(url)` | Retrieve the full indexed text of a URL |

### Tool details

**`crawl_url`**
- `url` – seed URL to crawl
- `max_pages` – cap on pages fetched (default 10, max 200)
- `max_depth` – link-hop depth from seed (default 1, max 5; 0 = seed only)
- `same_domain_only` – restrict to the seed domain (default `true`)

Returns a report: pages crawled / failed / skipped, list of indexed URLs, errors.

**`search`**
- `query` – free-text search query
- `top_k` – results to return (default 10, max 50)

Returns ranked hits with `url`, `title`, `snippet`, `score`, `domain`, `word_count`.

## Claude Desktop Integration

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "ai-web-search": {
      "command": "ai-web-search"
    }
  }
}
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `INDEX_DB_PATH` | `search_index.db` | SQLite database file path |
| `CRAWL_DELAY_SECONDS` | `1.0` | Politeness delay between requests to the same domain |
| `MAX_BODY_CHARS` | `50000` | Max characters extracted from each page body |
| `HTTP_TIMEOUT_SECONDS` | `15` | HTTP request timeout |
| `FETCH_MAX_CHARS` | `8000` | Max characters returned by `peek_document` |

Copy `.env.example` to `.env` and edit as needed.

## Crawl behaviour

- Respects `robots.txt` for every domain
- Skips binary file extensions (PDF, images, JS, CSS, …)
- Enforces a per-domain crawl delay (configurable)
- BFS frontier stored in SQLite — survives restarts; already-crawled URLs are never re-fetched
- `same_domain_only=true` (default) keeps crawls focused; set to `false` to follow external links

## Running tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

54 tests covering tokenizer, BM25 math, storage, crawler, indexer, and query processor.
