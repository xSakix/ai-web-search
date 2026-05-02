# AI Web Search – MCP Server

A web search engine exposed as an [MCP (Model Context Protocol)](https://modelcontextprotocol.io) server. It wraps multiple search backends, fetches and parses web pages, and caches results — all accessible to any MCP-compatible AI client.

## Features

- **Multiple providers** – DuckDuckGo (free, no key) + Brave Search API (optional)
- **Four MCP tools** – `web_search`, `search_news`, `search_images`, `fetch_page`, `batch_search`
- **TTL cache** – avoids redundant upstream calls
- **Page scraper** – fetch and clean any URL for deep research

## Quick Start

```bash
# 1. Install
pip install -e .

# 2. Configure (optional)
cp .env.example .env
# edit .env to add BRAVE_API_KEY if desired

# 3. Run
ai-web-search
```

## MCP Tools

| Tool | Description |
|------|-------------|
| `web_search(query, num_results?, region?, safe_search?, provider?)` | General web search |
| `search_news(query, num_results?, time_range?, region?)` | News search with optional time filter |
| `search_images(query, num_results?, region?, safe_search?)` | Image search (metadata) |
| `fetch_page(url, extract_links?, max_chars?)` | Fetch + parse a web page |
| `batch_search(queries, num_results?, region?)` | Run multiple searches in parallel |

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

## Architecture

```
MCP Server (stdio)
├── web_search      ─┐
├── search_news      ├─ Provider Registry ─┬─ DuckDuckGo (free)
├── search_images    │                     └─ Brave Search (API key)
├── fetch_page      ─┘
└── batch_search ── parallel web_search calls
        │
    TTL Cache (in-memory LRU)
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BRAVE_API_KEY` | | Brave Search API key (optional) |
| `SEARCH_PROVIDERS` | `duckduckgo,brave` | Provider priority order |
| `CACHE_TTL_SECONDS` | `300` | Cache entry lifetime |
| `CACHE_MAX_SIZE` | `512` | Max cached entries |
| `HTTP_TIMEOUT_SECONDS` | `15` | HTTP request timeout |
| `FETCH_MAX_CHARS` | `8000` | Max characters returned by fetch_page |
