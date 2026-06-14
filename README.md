# browsing-meta

[![Tests](https://img.shields.io/badge/tests-304%20passed-brightgreen)](https://github.com/Im-Busy/browsing-meta)
[![Python](https://img.shields.io/badge/python-3.13%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

> Meta-layer search intelligence wrapping SearXNG — Tavily-quality results on your own infrastructure.

Browsing-meta adds six processing layers to [SearXNG](https://docs.searxng.org/): intent detection, hybrid ranking, anti-bot content extraction, reliability gating, adaptive strategy, and multi-rollout verification. The result is agent-ready search output competitive with commercial APIs — running entirely on your own infrastructure.

---

## Quick Start

### MCP (AI Agents)

```json
{
  "mcpServers": {
    "browsing-meta": {
      "command": "npx",
      "args": ["browsing-meta"],
      "env": { "SEARXNG_URL": "http://localhost:8080" }
    }
  }
}
```

Requires Python 3.13+ and a running SearXNG instance.

### CLI

```bash
uvx browsing-meta search "latest AI research"
uvx browsing-meta search "Python vs Rust" --strategy explore
uvx browsing-meta extract "https://example.com/article"
```

### Library

```bash
pip install browsing-meta
```

```python
from browsing_meta import BrowsingMeta

meta = BrowsingMeta(searxng_url="http://localhost:8080")
result = await meta.search("quantum computing")
print(result.answer)
```

---

## MCP Tools

| Tool | Description |
|------|-------------|
| `search` | Full pipeline: intent analysis → SearXNG → ranking → extraction → reliability. Supports `time_range` (day/week/month/year), `max_sources`, and `strategy` (default/auto/explore/decompose). |
| `extract` | Fetch and extract a single URL with anti-bot bypass (Cloudflare Turnstile). Returns title, clean text, and extraction tier. |

---

## Client Configuration

### Claude Desktop

```json
{
  "mcpServers": {
    "browsing-meta": {
      "command": "uvx",
      "args": ["browsing-meta-mcp", "--searxng-url", "http://localhost:8080"]
    }
  }
}
```

### Cursor / VS Code

```json
{
  "mcpServers": {
    "browsing-meta": {
      "command": "npx",
      "args": ["browsing-meta"],
      "env": { "SEARXNG_URL": "http://localhost:8080" }
    }
  }
}
```

---

## Docker

Bundled SearXNG + Redis sidecar deployment:

```bash
docker compose up
```

SearXNG starts at `localhost:8080`, browsing-meta API at `localhost:8000`.

```bash
docker exec browsing-meta uv run browsing-meta search "your query"
```

---

## How It Works

Six processing layers wrap every search:

1. **Pre-Search** — Intent detection, browser profile rotation, language-aware params
2. **Post-Search** — URL normalization, tracking param stripping, RRF+BM25+MMR ranking
3. **Extraction** — 7-tier cascading extraction, anti-bot bypass, goal-oriented rational/evidence/summary
4. **Reliability** — Give-up detection (43 patterns EN+ZH), quality-gated retry, force synthesis
5. **Strategy** — Query classification, adaptive multi-angle exploration, recursive decomposition
6. **Verification** — Multi-rollout voting, consensus verification, LLM tie-breaking

---

## Development

```bash
git clone https://github.com/Im-Busy/browsing-meta.git
cd browsing-meta
uv sync

uv run pytest                  # 304 tests (287 unit + 17 integration)
uv run ruff check src/ tests/  # zero violations
uv run mypy src/               # zero errors
```

Tests require SearXNG at `localhost:8080`. Skip integration tests:

```bash
uv run pytest -m "not integration"
```

---

## License

MIT
