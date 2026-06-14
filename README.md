# browsing-meta

[![Tests](https://img.shields.io/badge/tests-304%20passed-brightgreen)](https://github.com/Im-Busy/browsing-meta)
[![Python](https://img.shields.io/badge/python-3.13%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

> Meta-layer search intelligence wrapping SearXNG — Tavily-quality results on your own infrastructure.

Browsing-meta adds six processing layers to [SearXNG](https://docs.searxng.org/): intent detection, hybrid ranking, anti-bot content extraction, reliability gating, adaptive strategy, and multi-rollout verification. The result is agent-ready search output competitive with commercial APIs — running entirely on your own infrastructure.

```mermaid
flowchart TD
    Q["Query"] --> L1

    subgraph L1["1. Pre-Search"]
        A["Intent detection<br/>Browser profiles<br/>Language detection"]
    end

    L1 --> SX["SearXNG Engine"]

    SX --> L2
    subgraph L2["2. Post-Search"]
        B["URL normalization<br/>RRF + BM25 + MMR"]
    end

    L2 --> L3
    subgraph L3["3. Extraction"]
        C["7-tier cascading<br/>Anti-bot bypass<br/>Goal-oriented summary"]
    end

    L3 --> L4
    subgraph L4["4. Reliability"]
        D["Give-up detection<br/>Quality-gated retry<br/>Force synthesis"]
    end

    L4 --> L5
    subgraph L5["5. Strategy"]
        E["Query classification<br/>Adaptive exploration<br/>Recursive decomposition"]
    end

    L5 --> L6
    subgraph L6["6. Verification"]
        F["Multi-rollout voting<br/>Consensus verification<br/>LLM tie-breaking"]
    end

    L6 --> A["Answer"]
```

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

Each search passes through six layers before returning an answer. The diagram above shows the full pipeline. Layers 1-4 run on every query; Layers 5-6 activate when `--strategy` or `--reliability` are set.

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
