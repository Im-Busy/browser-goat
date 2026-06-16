# browser-goat — AGENTS.md

> Meta-layer search intelligence wrapping SearXNG with layered processing inspired by SearchWala, local-deep-research, Marco-DeepResearch, Tongyi-DeepResearch, and Scrapling.

---

## Purpose

Turn SearXNG into a Tavily/Exa-competitive search backend for AI agents by wrapping it with six processing layers: Pre-Search, Post-Search, Extraction, Reliability, Strategy, and Verification. Each layer ports specific innovations from one of the four research reference repos in `C:\Dev\useful_repos\03-search-research\` plus Scrapling from `C:\Dev\useful_repos\07-web-scraping\`.

---

## Session Start Protocol

Every new AI session MUST read these files in order:

1. **`MEMORY.md`** — Persistent handover state: current phase, completed tasks, discovered issues, next session priorities
2. **`docs/blueprint.md`** — Product architecture and design — the single source of truth for what we're building
3. **`plans/01-core-pipeline.md`** — Phase 1 plan (current): Pre-Search + Post-Search + Extraction + Reliability
4. **`plans/02-strategy-intelligence.md`** — Phase 2 plan: Strategy layer + query classification
5. **`plans/03-verification-scaling.md`** — Phase 3 plan: Verification + multi-rollout + scaling

---

## Architecture

```
Agent Query
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 1: PRE-SEARCH   (from SearchWala + Tongyi)               │
│ • QueryIntelligence — intent detection, time sensitivity        │
│ • BrowserProfiles — 20 profiles rotated per request            │
│ • LanguageDetection — CJK-aware search parameters              │
└────────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ SEARXNG ENGINE          (existing, Docker at localhost:8080)    │
└────────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 2: POST-SEARCH  (from SearchWala)                        │
│ • URLPipeline — normalize, strip tracking params, dedup        │
│ • HybridRanker — RRF (k=60) + BM25+ (δ=1.0) + MMR (λ=0.7)    │
└────────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 3: EXTRACTION   (from SearchWala + Tongyi + Scrapling)   │
│ • ContentExtractor — 7-tier cascading extraction               │
│ • GoalOrientedExtractor — rational/evidence/summary per page   │
│ • ScraplingFetcher — anti-bot bypass with CF Turnstile        │
└────────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 4: RELIABILITY   (from Marco + SearchWala)               │
│ • GiveUpDetector — 43 regex patterns for agent failure         │
│ • QualityGate — retry on insufficient answers                  │
│ • ForceAnswer — synthesize when limits hit                     │
└────────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 5: STRATEGY      (from local-deep-research — Phase 2)    │
│ • QueryClassifier — Factual/Temporal/Comparison/HowTo/Research │
│ • AdaptiveExplorer — multi-angle candidate generation          │
│ • RecursiveDecomposer — complex → subtasks → aggregate         │
└────────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 6: VERIFICATION   (from Marco — Phase 3)                 │
│ • MultiRollout — N parallel searches with variation            │
│ • AnswerVoter — consensus voting across rollouts               │
│ • LLMVerifier — ties broken by verifier LLM                    │
└────────────────────────────┬────────────────────────────────────┘
                             ▼
                       Agent Answer
```

---

## Layer Details

### Layer 1 — Pre-Search
| Module | Source | What It Does |
|--------|--------|-------------|
| `query_intel.py` | SearchWala `query_intel.rs` | Intent detection (6 types), time sensitivity, entity extraction, complexity scoring |
| `browser_profiles.py` | SearchWala `config.rs` | 20 browser profiles (Chrome/Edge/Firefox/Safari), Sec-CH-UA headers, WAF bypass |
| `language_detect.py` | Tongyi `tool_search.py` | CJK detection → location/gl/hl parameter injection |

### Layer 2 — Post-Search
| Module | Source | What It Does |
|--------|--------|-------------|
| `url_pipeline.py` | SearchWala `url_utils.rs` | Single-pass normalize + blocklist + dedup + tracking param strip (30+ params) |
| `ranking.py` | SearchWala `ranking.rs` | RRF (k=60), BM25+ (δ=1.0), MMR diversity (λ=0.7), sentence-boundary chunking |

### Layer 3 — Extraction (CORE — not optional)
| Module | Source | What It Does |
|--------|--------|-------------|
| `content_extractor.py` | SearchWala `extractor.rs` | 7-tier: JSON-LD → structured CSS → semantic HTML5 → scored container → content elements → meta → body |
| `goal_oriented.py` | Tongyi `tool_visit.py` | Rational + Evidence + Summary structured output per page |
| `scrapling_fetcher.py` | Scrapling + scraper-in-one | Anti-bot bypass (CF Turnstile), adaptive parsing, stealth browser profiles |

### Layer 4 — Reliability
| Module | Source | What It Does |
|--------|--------|-------------|
| `give_up_detector.py` | Marco `context_manager.py` | 43 regex patterns (EN+ZH) for "I can't answer" / "no results" |
| `quality_gate.py` | SearchWala `llm.rs` | Retry when answer <80 chars or missing citations |
| `force_answer.py` | Marco `prompts/inference.py` | Force synthesis prompt when limits hit |

### Layer 5 — Strategy (Phase 2)
| Module | Source | What It Does |
|--------|--------|-------------|
| `query_classifier.py` | LDR `smart_decomposition_strategy.py` | LLM classifies query → routes to strategy |
| `adaptive_explorer.py` | LDR `adaptive_explorer.py` | 4 query-generation strategies, tracks performance, adapts |
| `recursive_decomposer.py` | LDR `recursive_decomposition_strategy.py` | Complex queries → subtasks → recursive solve → aggregate |

### Layer 6 — Verification (Phase 3)
| Module | Source | What It Does |
|--------|--------|-------------|
| `multi_rollout.py` | Marco `context_manager.py` | N parallel searches with parameter variation |
| `answer_voter.py` | Marco `context_manager.py` | Consensus voting, early stop at 4+ same answer |
| `llm_verifier.py` | Marco `context_manager.py` | LLM breaks ties with targeted verification |

---

## Tech Stack

- **Python 3.13+** with **uv** for package management
- **SearXNG** Docker at `localhost:8080` — engine dispatch layer
- **Scrapling** — anti-bot bypass with Cloudflare Turnstile solving
- **httpx** — async HTTP for all SearXNG calls
- **BeautifulSoup4 + lxml** — HTML parsing for content extraction
- **Playwright** — browser automation for Scrapling fallback

---

## Python Environment

Always use **uv**. Never use `python`, `pip`, `python3`, or `pip3` directly.

```bash
uv run <command>    # Run in project environment
uv add <package>    # Add dependency
uv sync            # Sync environment
```

---

## Coding Conventions

- Type hints on ALL function signatures and return types
- `pathlib.Path` over `os.path`
- Async-first: all I/O uses `httpx.AsyncClient` or `asyncio`
- Each module under ~400 lines; split if larger
- Pydantic models for all structured data (search results, extracted content, answers)
- Follow `.opencode/standards/workspace-conventions.md` for base conventions

---

## Testing Standards

- Every public function must have at least one test
- Tests mirror source: `src/browser_goat/pre_search/query_intel.py` → `tests/pre_search/test_query_intel.py`
- Run: `uv run pytest`
- Coverage target: ≥80%

---

## Quality Gate Protocol

Before declaring any task complete:

```bash
uv run ruff check src/ tests/        # Zero violations
uv run mypy src/                      # Zero errors
uv run pytest                         # All pass
```

---

## Reference Repos (Read-Only Sources)

| Repo | Path | What We Port From |
|------|------|-------------------|
| **SearchWala** | `C:\Dev\useful_repos\03-search-research\SearchWala\` | Browser profiles, query intel, ranking, extraction, URL pipeline, quality gate |
| **local-deep-research** | `C:\Dev\useful_repos\03-search-research\local-deep-research\` | Query classification, adaptive exploration, recursive decomposition |
| **Marco-DeepResearch** | `C:\Dev\useful_repos\03-search-research\Marco-DeepResearch\` | Give-up detection, multi-rollout voting, force answer, verification |
| **Tongyi-DeepResearch** | `C:\Dev\useful_repos\03-search-research\Tongyi-DeepResearch\` | Language-aware params, goal-oriented extraction, ReSum summarization |
| **Scrapling** | `C:\Dev\useful_repos\07-web-scraping\Scrapling\` | Anti-bot bypass, Cloudflare Turnstile, adaptive parsing |
| **scraper-in-one** | `C:\Dev\projects\scraper-in-one\` | 6-tier progressive escalation pattern, ScrapeRouter pattern |

---

## File Creation Guidelines

Before creating a new file, ask: can this content be added to an existing file instead?

- Find the canonical parent file for the topic
- Add as a subsection — append, don't sprawl
- Only create new files when no parent exists, new category, or parent exceeds ~400 lines

---

## Anti-Rationalization Guardrails

| Rationalization | Reality |
|----------------|---------|
| "I'll add tests after it works" | Untested code is production debt |
| "One more tweak will fix it" | Adding without validation adds noise. Verify, then add |
| "I can skip the edge cases" | Edge cases are where bugs live |
| "I'll add type hints later" | Type hints ARE the documentation for search pipeline data |

---

## Distribution Plan

**Target Consumers**: AI agents (primary), Python developers (secondary)
**Deployment Model**: Library + CLI + service sidecar + MCP server
**Platforms**: All (Windows, macOS, Linux, server)

### Channels Evaluated

| Channel | Decision | Reason |
|---------|:---:|--------|
| **PyPI** | ✅ Required | Python project, library usage model — `pip install browser-goat` |
| **uvx** | ✅ Required | Python CLI with zero-install UX — `uvx browser-goat` via `[project.scripts]` |
| **Docker** | ✅ Required | External service dependency (SearXNG), sidecar deployment model — bundles SearXNG + browser-goat |
| **MCP Server** | ✅ Required | Primary consumer is AI agents — MCP is the agent-to-tool protocol |
| **npm/npx** | ✅ Required | MCP-native distribution channel — thin Node.js wrapper that exposes the Python backend as an MCP server, enabling `npx browser-goat` for zero-install agent usage |
| **Homebrew** | ✅ Recommended | macOS developer audience, low-effort formula |
| **conda-forge** | ❌ Skipped | Pure Python — PyPI covers conda users |
| **Cargo** | ❌ Skipped | Not a Rust project (see Module Language Profile below) |
| **Scoop/Chocolatey/Winget** | ❌ Skipped | Agent tool + library, not a desktop app or standalone binary |
| **apt/dnf/pacman** | ❌ Skipped | Developer tool, not a distro-maintained system package |

### Channel Architecture

```
                    ┌──────────────────────────────┐
                    │       AI Agent (Claude,       │
                    │     Cursor, OpenCode...)      │
                    └──────────┬───────────────────┘
                               │ MCP protocol (stdio)
                    ┌──────────▼───────────────────┐
                    │   npm package (thin wrapper)  │ ← npm/npx channel
                    │   npx browser-goat           │
                    │   → spawns Python backend     │
                    └──────────┬───────────────────┘
                               │ subprocess
                    ┌──────────▼───────────────────┐
                    │   Python library + CLI        │ ← PyPI + uvx channels
                    │   pip install browser-goat   │
                    │   uvx browser-goat           │
                    └──────────┬───────────────────┘
                               │ HTTP
                    ┌──────────▼───────────────────┐
                    │   SearXNG (Docker sidecar)    │ ← Docker channel
                    │   docker compose up           │
                    └──────────────────────────────┘
```

- **PyPI + uvx**: Python library and CLI entry point. `[project.scripts]` exposes the `browser-goat` command. uvx provides zero-install for Python developers.
- **npm/npx**: Thin Node.js MCP server that spawns the Python CLI as a subprocess. This is the agent interface — `npx browser-goat` in an MCP client config. The npm package contains only the MCP glue (~50 lines of TypeScript); all logic lives in the Python package.
- **Docker**: `docker-compose.yml` bundles SearXNG + browser-goat as a sidecar. Single `docker compose up` for self-hosted deployment.
- **MCP Server**: The protocol surface — defined as a JSON schema of tools (`search`, `extract`, `verify`). Implemented by both the npm wrapper (for npx agents) and a Python-native MCP server (for uvx/pip agents).
- **Homebrew**: Formula that installs the Python CLI via pipx or uv, for macOS developers who prefer `brew install`.

### Module Language Profile

| Module | Current | Would Benefit From | Reason | Threshold |
|--------|---------|:---:|--------|:---:|
| `ranking.py` | Python | Go | BM25+/MMR is CPU-bound at scale | >1,000 results |
| All other 19 modules | Python | — | I/O-bound (network, page fetch, LLM call dominate) | — |

**Rewrite Evaluation**: 1 / 20 modules could benefit. Port only `ranking.py` to Go if threshold is reached. No full rewrite.
