# Quickstart

Get your first result in 5 minutes.

## Prerequisites

A running SearXNG instance. Start one with Docker:

```bash
docker compose up -d redis searxng
```

## CLI Search

Search the web from your terminal:

```bash
browser-goat search "latest developments in quantum computing"
```

A single command runs the full pipeline and returns a synthesized answer with citations.

## CLI Extraction

Pull clean content from any URL:

```bash
browser-goat extract "https://example.com"
```

Returns full extracted plain text in JSON. Browser-backed tiers attempt
anti-bot recovery when installed; access is not guaranteed.

## Library Usage

Drop browser-goat into any Python project:

```python
from browser_goat import BrowserGoat

async with BrowserGoat(searxng_url="http://localhost:8082") as goat:
    result = await goat.search("Python async patterns")
    print(result.answer)
```

Async from the ground up — pairs naturally with httpx, FastAPI, or any modern stack.

## MCP Connection

Wire it into your AI agent's MCP config:

```json
{
  "mcpServers": {
    "browser-goat": {
      "command": "npx",
      "args": ["browser-goat"],
      "env": { "SEARXNG_URL": "http://localhost:8082" }
    }
  }
}
```

Your agent can now run searches and extract pages without leaving its MCP session.
The npm wrapper requires Python with `browser-goat` installed. Set `PYTHON_CMD`
to that interpreter; see [npm prerequisites](../npm/README.md).

---

**What's next:** Dive deeper with the [CLI Reference](cli.md), [Python Library](library.md), or [MCP Integration](mcp.md) guide.
