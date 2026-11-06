# Quickstart

Run these commands from a source checkout.

## Prerequisites

Install Python 3.13+, uv, and Docker with Compose. Sync the checkout and start
the bundled SearXNG backend, which enables JSON search:

```bash
uv sync --locked
docker compose up -d redis searxng
```

## CLI Search

Search the web from your terminal:

```bash
uv run browser-goat search "Python asyncio documentation" --max-sources 2
```

The default search returns JSON containing source links, bounded text excerpts,
an answer listing up to five source summaries, quality checks, and metrics.
It does not synthesize a narrative answer. See
[behavior and limits](../README.md#behavior-and-limits) for the optional library
callback and verification modes.

## CLI Extraction

Fetch and extract text from an HTTP or HTTPS URL:

```bash
uv run browser-goat extract "https://example.com"
```

Returns extracted text or an explicit failure in JSON. Extraction does not
require SearXNG. Browser-backed tiers need the binaries and system libraries
listed in [installation](install.md); access to a site is not guaranteed.

## Library Usage

Run this example in the prepared checkout environment:

```python
import asyncio
from browser_goat import BrowserGoat

async def main() -> None:
    async with BrowserGoat(searxng_url="http://localhost:8082") as goat:
        result = await goat.search("Python async patterns", max_sources=2)
        print(result.answer)

asyncio.run(main())
```

## MCP Connection

For a client supporting `mcpServers`, launch the prepared checkout. Replace
`/path/to/browser-goat` with its absolute path:

```json
{
  "mcpServers": {
    "browser-goat": {
      "command": "uv",
      "args": ["run", "--project", "/path/to/browser-goat", "browser-goat-mcp"],
      "env": { "SEARXNG_URL": "http://localhost:8082" }
    }
  }
}
```

The client communicates over stdio. SearXNG uses host port `8082`; the separate
Compose HTTP JSON API uses `8003` and is not an MCP endpoint. Client schemas
differ; see [MCP integration](mcp.md) before adapting this example.

For registry launchers, see [installation](install.md) and
[npm prerequisites](../npm/README.md). A registry install does not establish
that it contains this checkout's revision.
