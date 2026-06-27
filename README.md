# browser-goat — Production-grade web search for AI agents

[![Tests](https://img.shields.io/badge/tests-304%20passed-brightgreen)](https://github.com/Im-Busy/browser-goat)
[![Python](https://img.shields.io/badge/python-3.13%2B-blue?logo=python)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![PyPI](https://img.shields.io/badge/pypi-browser--goat-22c55e?logo=pypi)](https://pypi.org/project/browser-goat)

![divider](https://readme-svg-wave-divider-generator.vercel.app/wave?type=sine&width=1200&height=100&amplitude=20&frequency=2&layers=2&color_top=22c55e&color_bottom=14532d&opacity=1&flip=false&gradient=false&mirror=false&animate=false)

> Six-stage search pipeline around SearXNG: query intent detection, hybrid BM25+MMR ranking, anti-bot content extraction, quality-gated retry, adaptive exploration, and multi-rollout consensus verification — running entirely on your own infrastructure.

## Why browser-goat?

SearXNG is powerful but raw — it returns search results, not answers. browser-goat wraps it with six processing layers that turn those results into verified, structured answers that AI agents can trust. Each layer ports specific innovations from SearchWala, local-deep-research, Marco-DeepResearch, Tongyi-DeepResearch, and Scrapling.

![divider](https://readme-svg-wave-divider-generator.vercel.app/wave?type=sine&width=1200&height=100&amplitude=20&frequency=2&layers=2&color_top=22c55e&color_bottom=14532d&opacity=1&flip=false&gradient=false&mirror=false&animate=false)

## Architecture

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

    style L1 fill:#22c55e,stroke:#166534,color:#fff
    style L2 fill:#16a34a,stroke:#15803d,color:#e0e0e0
    style L3 fill:#15803d,stroke:#14532d,color:#e0e0e0
    style L4 fill:#14532d,stroke:#166534,color:#e0e0e0
    style L5 fill:#166534,stroke:#14532d,color:#e0e0e0
    style L6 fill:#052e16,stroke:#22c55e,color:#e0e0e0
```

| Layer | What It Does | Source |
|-------|-------------|--------|
| **Pre-Search** | Intent detection (6 types), 20 browser profiles, CJK-aware parameters | SearchWala + Tongyi |
| **Post-Search** | URL normalization, RRF (k=60) + BM25+ + MMR (λ=0.7) | SearchWala |
| **Extraction** | 7-tier cascading, goal-oriented summaries, anti-bot bypass | SearchWala + Scrapling |
| **Reliability** | 43 give-up patterns, quality-gated retry, force synthesis | Marco + SearchWala |
| **Strategy** | Query classification, adaptive exploration, recursive decomposition | local-deep-research |
| **Verification** | Multi-rollout voting, consensus verification, LLM tie-breaking | Marco |

![divider](https://readme-svg-wave-divider-generator.vercel.app/wave?type=sine&width=1200&height=100&amplitude=20&frequency=2&layers=2&color_top=22c55e&color_bottom=14532d&opacity=1&flip=false&gradient=false&mirror=false&animate=false)

## Quick Start

### MCP (AI Agents)

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

Requires Python 3.13+ and a running SearXNG instance.

### CLI

```bash
uvx browser-goat search "latest AI research"
uvx browser-goat search "Python vs Rust" --strategy explore
uvx browser-goat extract "https://example.com/article"
```

Run `uvx browser-goat --guide` for full documentation.

### Library

```python
from browser_goat import BrowserGoat

meta = BrowserGoat(searxng_url="http://localhost:8080")
result = await meta.search("quantum computing")
print(result.answer)
```

## MCP Tools

| Tool | Description |
|------|-------------|
| `search` | Full pipeline: intent -> SearXNG -> ranking -> extraction -> reliability. Supports `time_range`, `max_sources`, `strategy`. |
| `extract` | Fetch and extract a single URL with anti-bot bypass (Cloudflare Turnstile). |

See [CLIENTS.md](CLIENTS.md) for platform-specific MCP configuration.

## Docker

```bash
docker compose up   # SearXNG at localhost:8080, API at localhost:8000
```

## Development

```bash
git clone https://github.com/Im-Busy/browser-goat.git && cd browser-goat && uv sync
uv run pytest                  # 304 tests
uv run ruff check src/ tests/  # zero violations
uv run mypy src/               # zero errors
```

## License

MIT
