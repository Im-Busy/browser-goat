# browsing-meta

> Meta-layer search intelligence wrapping SearXNG. One API call. One SearXNG backend. Tavily-quality results.

[![tests](https://img.shields.io/badge/tests-287%20passed-brightgreen)](https://github.com/Im-Busy/browsing-meta)
[![ruff](https://img.shields.io/badge/ruff-0%20violations-brightgreen)](https://github.com/Im-Busy/browsing-meta)
[![mypy](https://img.shields.io/badge/mypy-0%20errors-brightgreen)](https://github.com/Im-Busy/browsing-meta)
[![python](https://img.shields.io/badge/python-3.13%2B-blue)](https://python.org)

---

## What It Does

Browsing-meta wraps [SearXNG](https://docs.searxng.org/) with six processing layers ported from battle-tested open-source projects (SearchWala, local-deep-research, Marco-DeepResearch, Tongyi-DeepResearch, Scrapling). The result: SearXNG becomes competitive with commercial search APIs (Tavily, Exa) for AI agent use.

| Layer | What It Does |
|-------|-------------|
| **Pre-Search** | Intent detection, browser profile rotation, language-aware params |
| **Post-Search** | URL normalization, tracking param stripping, RRF+BM25+MMR ranking |
| **Extraction** | 7-tier cascading content extraction, anti-bot bypass (CF Turnstile) |
| **Reliability** | Give-up detection, quality-gated retry, force-answer synthesis |
| **Strategy** | Query classification, adaptive multi-angle exploration, recursive decomposition |
| **Verification** | Multi-rollout voting, consensus verification, LLM tie-breaking |

---

## Installation

### MCP Server (AI Agents)

The primary interface for AI agents. Add to your MCP client config:

```json
{
  "mcpServers": {
    "browsing-meta": {
      "command": "npx",
      "args": ["browsing-meta"],
      "env": {
        "SEARXNG_URL": "http://localhost:8080"
      }
    }
  }
}
```

Requires Python 3.13+ and `browsing-meta` installed via pip/uv.

### CLI (Zero-Install)

```bash
uvx browsing-meta search "latest AI research 2026"
uvx browsing-meta search "Python vs Rust" --strategy explore --reliability high
uvx browsing-meta extract "https://example.com/article"
uvx browsing-meta verify "quantum computing breakthroughs"
```

### pip / uv

```bash
pip install browsing-meta
# or
uv add browsing-meta
```

Then use as a library:

```python
from browsing_meta import BrowsingMeta

meta = BrowsingMeta(searxng_url="http://localhost:8080")
result = await meta.search("What is quantum computing?")

print(result.answer)
for source in result.sources:
    print(f"  [{source.url}] {source.summary}")
```

### Docker

```bash
docker compose up
```

Starts SearXNG + Redis + browsing-meta. Access at `localhost:8000`.

```bash
docker exec browsing-meta uv run browsing-meta search "climate change solutions"
```

### Homebrew (macOS)

```bash
brew install browsing-meta
```

---

## Prerequisites

- **Python 3.13+**
- **SearXNG** — running instance (default: `http://localhost:8080`). Use `docker compose up` for a bundled setup.

---

## Architecture

```
Agent Query
    │
    ▼
┌────────────────────────────────────────────────────────────────┐
│ LAYER 1: PRE-SEARCH   (SearchWala + Tongyi)                   │
│ • QueryIntelligence — intent, time sensitivity, entities      │
│ • BrowserProfiles — 20 profiles rotated per request           │
│ • LanguageDetection — CJK-aware search parameters              │
└────────────────────────────────────────────────────────────────┘
    │               ▼
    │   SEARXNG ENGINE
    │               ▼
    ▼
┌────────────────────────────────────────────────────────────────┐
│ LAYER 2: POST-SEARCH  (SearchWala)                            │
│ • URLPipeline — normalize, strip tracking, dedup              │
│ • HybridRanker — RRF (k=60) + BM25+ (δ=1.0) + MMR (λ=0.7)   │
└────────────────────────────────────────────────────────────────┘
    ▼
┌────────────────────────────────────────────────────────────────┐
│ LAYER 3: EXTRACTION   (SearchWala + Tongyi + Scrapling)      │
│ • ContentExtractor — 7-tier cascading extraction              │
│ • GoalOrientedExtractor — rational/evidence/summary           │
│ • ScraplingFetcher — anti-bot bypass, CF Turnstile           │
└────────────────────────────────────────────────────────────────┘
    ▼
┌────────────────────────────────────────────────────────────────┐
│ LAYER 4: RELIABILITY   (Marco + SearchWala)                   │
│ • GiveUpDetector — 43 regex patterns for agent failure        │
│ • QualityGate — retry on insufficient answers                 │
│ • ForceAnswer — synthesize when limits hit                    │
└────────────────────────────────────────────────────────────────┘
    ▼
┌────────────────────────────────────────────────────────────────┐
│ LAYER 5: STRATEGY      (local-deep-research)                  │
│ • QueryClassifier — factual/temporal/comparison/howto/research│
│ • AdaptiveExplorer — multi-angle candidate generation         │
│ • RecursiveDecomposer — complex → subtasks → aggregate        │
└────────────────────────────────────────────────────────────────┘
    ▼
┌────────────────────────────────────────────────────────────────┐
│ LAYER 6: VERIFICATION   (Marco)                               │
│ • MultiRollout — N parallel searches with variation           │
│ • AnswerVoter — consensus voting across rollouts              │
│ • LLMVerifier — ties broken by verifier LLM                   │
└────────────────────────────────────────────────────────────────┘
    │
    ▼
Agent Answer
```

---

## Attribution

Every module traces back to a specific open-source project:

| Module | Ported From |
|--------|-------------|
| `query_intel.py`, `browser_profiles.py`, `ranking.py`, `url_pipeline.py`, `content_extractor.py`, `quality_gate.py` | [SearchWala](https://github.com/djpilot/searchwala) |
| `language_detect.py`, `goal_oriented.py` | [Tongyi-DeepResearch](https://github.com/modelscope/Tongyi-DeepResearch) |
| `give_up_detector.py`, `force_answer.py`, `multi_rollout.py`, `answer_voter.py`, `llm_verifier.py` | [Marco-DeepResearch](https://github.com/marcobellaccini/Marco-DeepResearch) |
| `query_classifier.py`, `adaptive_explorer.py`, `recursive_decomposer.py` | [local-deep-research](https://github.com/LearningCircuit/local-deep-research) |
| `scrapling_fetcher.py` | [Scrapling](https://github.com/D4Vinci/Scrapling) |

---

## License

MIT
