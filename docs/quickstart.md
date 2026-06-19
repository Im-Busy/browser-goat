# Quickstart

Get your first result in 5 minutes.

## Prerequisites

A running SearXNG instance. Start one with Docker:

```bash
docker run -d -p 8080:8080 searxng/searxng
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
browser-goat extract "https://example.com/article"
```

Bypasses anti-bot protections and returns clean markdown from the page.

## Library Usage

Drop browser-goat into any Python project:

```python
from browser_goat import BrowserGoat

goat = BrowserGoat(searxng_url="http://localhost:8080")
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
      "env": { "SEARXNG_URL": "http://localhost:8080" }
    }
  }
}
```

Your agent can now run searches and extract pages without leaving its MCP session.

---

**What's next:** Dive deeper with the [CLI Reference](cli.md), [Python Library](library.md), or [MCP Integration](mcp.md) guide.
