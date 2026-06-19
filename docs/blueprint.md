# browser-goat — Product Blueprint

> **Version**: 0.1.0 | **Status**: Planning | **Date**: 2026-06-14

---

## 1. Problem Statement

SearXNG is a capable meta-search engine, but it feels worse than commercial alternatives (Tavily, Exa) when used as a search backend for AI agents. The gap is not in SearXNG's core engine dispatch — it's in everything that happens **before and after** the search.

| What Tavily/Exa Do | What Bare SearXNG Does | The Gap |
|---|---|---|
| Extract full article text | Return URL + snippet | **Content** |
| Score results by relevance | Raw engine order | **Ranking** |
| Synthesize AI answers | Nothing | **Synthesis** |
| WAF/bot bypass | Basic user-agent rotation | **Stealth** |
| Query intent analysis | Nothing | **Intelligence** |
| Goal-oriented extraction | Nothing | **Structure** |
| Failure detection + retry | Nothing | **Reliability** |

**browser-goat closes every gap** by wrapping SearXNG with six processing layers, each porting innovations from battle-tested open-source projects.

---

## 2. Product Vision

**browser-goat** is a Python meta-layer that wraps SearXNG and makes it competitive with Tavily and Exa for AI agent use. It does NOT replace SearXNG — it augments it.

### Core Principles

1. **SearXNG is the engine, not the product** — SearXNG handles multi-engine dispatch. Everything else is pre/post processing.
2. **Stand on shoulders** — Every innovation is ported from an existing open-source project with proven results. No reinvention.
3. **Layer, don't monolith** — Each layer is independently testable, swappable, and can be used without the others.
4. **Python-first** — Even Rust innovations (SearchWala) are ported to Python. Python is the integration language.
5. **Scrapling + Tongyi extraction are CORE** — Anti-bot bypass and structured extraction are not optional; they're what make the output "agent-ready."

### One-Line Pitch

> "One API call. One SearXNG backend. Tavily-quality results."

---

## 3. Architecture Overview

```
                         ┌──────────────────┐
                         │   Agent / LLM    │
                         └────────┬─────────┘
                                  │ search("What is the latest on...")
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     browser-goat ROUTER                             │
│                     BrowserGoat.search(query)                       │
└─────────────────────────────────────────────────────────────────────┘
         │           │           │           │           │
         ▼           ▼           ▼           ▼           ▼
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│ LAYER 1  │ │ LAYER 2  │ │ LAYER 3  │ │ LAYER 4  │ │ LAYER 5+6│
│Pre-Search│ │Post-Srch │ │Extraction│ │Reliability│ │Strategy+ │
│          │ │          │ │  (CORE)  │ │          │ │Verify    │
└────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘
     │            │            │            │            │
     ▼            ▼            ▼            ▼            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         SEARXNG (Docker)                             │
│                    http://localhost:8080/search?q=...                │
└─────────────────────────────────────────────────────────────────────┘
```

### Layer Summary

| # | Layer | Phase | Source Repos | What It Does |
|---|-------|-------|-------------|-------------|
| 1 | **Pre-Search** | Phase 1 | SearchWala, Tongyi | Intent detection, browser profiles, language-aware params |
| 2 | **Post-Search** | Phase 1 | SearchWala | URL normalization, tracking param stripping, RRF+BM25+MMR ranking |
| 3 | **Extraction** | Phase 1 | SearchWala, Tongyi, Scrapling | 7-tier content extraction, goal-oriented structured output, anti-bot bypass |
| 4 | **Reliability** | Phase 1 | Marco, SearchWala | Give-up detection, quality-gated retry, force-answer synthesis |
| 5 | **Strategy** | Phase 2 | local-deep-research | Query classification, adaptive exploration, recursive decomposition |
| 6 | **Verification** | Phase 3 | Marco | Multi-rollout voting, consensus verification, LLM tie-breaking |

---

## 4. Data Flow (End-to-End)

```
User Query: "What's the latest research on CRISPR gene editing for cancer treatment?"

Step 1 — PRE-SEARCH (Layer 1)
┌─────────────────────────────────────────────────────────────────┐
│ QueryIntel.analyze("What's the latest...")                      │
│   → intent: RESEARCH                                            │
│   → time_sensitive: true (keyword: "latest")                    │
│   → entities: ["CRISPR", "gene editing", "cancer treatment"]    │
│   → complexity: COMPLEX                                         │
│   → optimal_sources: 25-30                                      │
│                                                                 │
│ BrowserProfiles.get_profile()                                    │
│   → Chrome 147 on Windows, Sec-CH-UA, Accept-Language            │
│                                                                 │
│ LanguageDetect.detect("What's the latest...")                   │
│   → lang: en, location: United States, gl: us, hl: en           │
│                                                                 │
│ Enriched Query: "What's the latest research on CRISPR gene      │
│   editing for cancer treatment 2026"                             │
│ SearXNG params: engines=google,bing,scholar, engines=general,   │
│   time_range=year, language=en                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
Step 2 — SEARXNG
┌─────────────────────────────────────────────────────────────────┐
│ GET http://localhost:8080/search?q=...&format=json              │
│   → 25 raw results with title, url, content (snippets)          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
Step 3 — POST-SEARCH (Layer 2)
┌─────────────────────────────────────────────────────────────────┐
│ URLPipeline.process(results)                                     │
│   → normalize URLs                                               │
│   → strip tracking params (utm_source, ref, fbclid, ...)        │
│   → remove blocked domains (pinterest, quora, ...)              │
│   → deduplicate by normalized URL                               │
│   INPUT: 25 raw results → OUTPUT: 22 unique, clean results      │
│                                                                 │
│ HybridRanker.rank(results, query)                                │
│   Stage A: RRF (k=60) — cross-engine consensus                  │
│   Stage B: BM25+ (δ=1.0) — paragraph-level relevance            │
│   Stage D: MMR (λ=0.7) — source diversity                       │
│   INPUT: 22 results → OUTPUT: 15 ranked, diverse results        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
Step 4 — EXTRACTION (Layer 3) — CORE
┌─────────────────────────────────────────────────────────────────┐
│ For each of 15 ranked URLs (concurrent, max 8 workers):          │
│                                                                 │
│ ScraplingFetcher.fetch(url)                                      │
│   → Try Scrapling with stealth browser profile                   │
│   → If CF Turnstile detected → solve automatically              │
│   → If blocked → rotate profile, retry (max 3)                   │
│   → Fallback: plain httpx GET                                   │
│   OUTPUT: raw HTML                                               │
│                                                                 │
│ ContentExtractor.extract(html, url)                              │
│   Tier 1: Try JSON-LD (schema.org/Article)                       │
│   Tier 2: Try structured CSS selectors (35+ CMS patterns)       │
│   Tier 3: Try semantic HTML5 (article, main)                     │
│   Tier 4: Try scored container (text density + link penalty)    │
│   Tier 5: Try content elements (p, h1-h6)                        │
│   Tier 6: Try meta/og:description                                │
│   Tier 7: Try full body (last resort)                            │
│   OUTPUT: clean article text + title + metadata                  │
│                                                                 │
│ GoalOrientedExtractor.extract(text, query)                       │
│   → Rational: why this page answers the query                   │
│   → Evidence: the specific text passages that are relevant       │
│   → Summary: condensed 2-3 sentence summary                     │
│   OUTPUT: structured {rational, evidence, summary}               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
Step 5 — RELIABILITY (Layer 4)
┌─────────────────────────────────────────────────────────────────┐
│ GiveUpDetector.check(answer)                                     │
│   → 43 regex patterns: "I couldn't find", "no results",         │
│     "unable to determine", "insufficient information"...         │
│   → If triggered → force retry or rephrase query                │
│                                                                 │
│ QualityGate.check(answer)                                        │
│   → answer length < 80 chars → insufficient → retry             │
│   → no citations/sources → insufficient → retry                 │
│   → max 1 retry per query                                       │
│                                                                 │
│ ForceAnswer.synthesize(results, query)                           │
│   → When limits hit and still no good answer                    │
│   → Explicit prompt: "Synthesize a final answer from these      │
│     sources. Include citations. If truly insufficient,          │
│     state what's missing."                                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
Step 6 — RESPONSE
┌─────────────────────────────────────────────────────────────────┐
│ {                                                               │
│   "answer": "Recent CRISPR research for cancer treatment        │
│     focuses on... [with inline citations]",                     │
│   "sources": [{                                                 │
│     "url": "https://...",                                       │
│     "title": "...",                                             │
│     "rational": "This 2026 Nature paper details...",            │
│     "evidence": "Key finding: in vivo trials showed...",        │
│     "summary": "Phase II trial results for CRISPR-Cas12..."     │
│   }, ...],                                                      │
│   "query_intent": "research",                                   │
│   "engines_used": ["google", "bing", "scholar"],                │
│   "total_sources_found": 22,                                    │
│   "total_sources_used": 15,                                     │
│   "extraction_success_rate": 0.93,                              │
│   "pipeline_latency_ms": 3200                                   │
│ }                                                               │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5. Reference Repo Attribution

Every module in browser-goat traces back to a specific source. This is the lineage table:

### Phase 1 Sources

| browser-goat Module | Source Repo | Source File | Lines | Innovation |
|---|---|---|---|---|
| `pre_search/query_intel.py` | SearchWala | `src/query_intel.rs:71-344` | 274 | Intent detection (6 types), time sensitivity, entity extraction, complexity scoring |
| `pre_search/browser_profiles.py` | SearchWala | `src/config.rs:107-401` | 295 | 20 browser profiles (Chrome/Edge/Firefox/Safari), Sec-CH-UA headers, Accept-Encoding |
| `pre_search/language_detect.py` | Tongyi-DeepResearch | `inference/tool_search.py:39-56` | 18 | CJK detection → location/gl/hl parameter injection |
| `post_search/url_pipeline.py` | SearchWala | `src/url_utils.rs:98-183` | 86 | Single-pass normalize + blocklist + dedup + tracking param strip (30+ params) |
| `post_search/ranking.py` | SearchWala | `src/ranking.rs:90-533` | 444 | RRF (k=60), BM25+ (δ=1.0), MMR (λ=0.7), sentence-boundary chunking, 15% overlap |
| `extraction/content_extractor.py` | SearchWala | `src/extractor.rs:143-832` | 690 | 7-tier cascading: JSON-LD → CSS → HTML5 → scored → elements → meta → body |
| `extraction/goal_oriented.py` | Tongyi-DeepResearch | `inference/tool_visit.py:27-141` | 115 | Rational + Evidence + Summary structured output per page |
| `extraction/scrapling_fetcher.py` | Scrapling + scraper-in-one | Scrapling SKILL.md + `router.py` | New | Anti-bot bypass, CF Turnstile, adaptive parsing, 6-tier escalation |
| `reliability/give_up_detector.py` | Marco-DeepResearch | `marco/agent/context_manager.py:13-45` | 33 | 43 regex patterns (EN+ZH) for "I can't answer" detection |
| `reliability/quality_gate.py` | SearchWala | `src/llm.rs:1678-1700` | 23 | Retry on answer <80 chars or no citations |
| `reliability/force_answer.py` | Marco-DeepResearch | `marco/prompts/inference.py:57-70` | 14 | Force synthesis prompt when limits hit |

### Phase 2 Sources

| browser-goat Module | Source Repo | Source File | Innovation |
|---|---|---|---|
| `strategy/query_classifier.py` | local-deep-research | `strategies/smart_decomposition_strategy.py` | LLM classifies query type → routes to strategy |
| `strategy/adaptive_explorer.py` | local-deep-research | `candidate_exploration/adaptive_explorer.py` | 4 query-generation strategies, performance tracking, adaptation |
| `strategy/recursive_decomposer.py` | local-deep-research | `strategies/recursive_decomposition_strategy.py` | Complex queries → subtasks → recursive solve → aggregate |

### Phase 3 Sources

| browser-goat Module | Source Repo | Source File | Innovation |
|---|---|---|---|
| `verification/multi_rollout.py` | Marco-DeepResearch | `marco/agent/context_manager.py:254-328` | N parallel searches with variation |
| `verification/answer_voter.py` | Marco-DeepResearch | `marco/agent/context_manager.py:274-284` | Consensus voting, early stop at 4+ same |
| `verification/llm_verifier.py` | Marco-DeepResearch | `marco/agent/context_manager.py:286-328` | LLM breaks ties with targeted verification |

---

## 6. Key Design Decisions

### 6.1 Python Ports, Not Rust Binaries
SearchWala is Rust. We port the algorithms to Python rather than running SearchWala as a subprocess. Reasons:
- Easier integration with the Python agent ecosystem
- No binary compilation/management overhead
- The algorithms (RRF, BM25, content extraction) are simple math — porting is straightforward
- We only need the algorithms, not the full Rust async runtime

### 6.2 SearXNG Stays as the Engine
We don't replace SearXNG's engine dispatch. SearXNG already handles 70+ engines, rate limiting, caching, and JSON API. Replacing that would be months of work for marginal gain. Instead, we wrap it.

### 6.3 Scrapling Is Core
Content extraction without anti-bot bypass fails on ~30% of sites (those behind Cloudflare, Akamai, etc.). Scrapling is the only open-source solution that handles Cloudflare Turnstile. It MUST be in the core pipeline.

### 6.4 Goal-Oriented Extraction Is Core
Raw extracted text is not agent-friendly. An agent needs to know WHY a page is relevant and WHAT specific evidence it contains. Tongyi's rational/evidence/summary pattern is lightweight (LLM call per page) and dramatically improves answer quality. It MUST be in the core pipeline.

### 6.5 Phase-Gated Implementation
- Phase 1 delivers a working end-to-end product (layers 1-4)
- Phase 2 adds strategy intelligence (smarter, not just faster)
- Phase 3 adds verification (more reliable, not just smarter)
Each phase is independently shippable and useful.

---

## 7. API Design

### Primary API

```python
from browser_goat import BrowserGoat

meta = BrowserGoat(
    searxng_url="http://localhost:8080",
    llm_config={...},  # For goal-oriented extraction
)

result = await meta.search("What is the latest on...")
```

### Result Schema

```python
class SearchResult(BaseModel):
    answer: str                          # Synthesized answer with citations
    sources: list[ExtractedSource]       # All extracted sources
    query_intent: str                    # fact/temporal/person/comparison/howto/research
    engines_used: list[str]              # Which SearXNG engines were queried
    total_sources_found: int             # Before filtering/ranking
    total_sources_used: int              # After ranking, used for answer
    extraction_success_rate: float       # Fraction of URLs successfully extracted
    pipeline_latency_ms: int             # End-to-end latency
    reliability_checks: ReliabilityInfo  # Give-up detection, quality gate results

class ExtractedSource(BaseModel):
    url: str
    title: str
    rational: str                        # Why relevant
    evidence: str                        # The relevant text
    summary: str                         # Condensed summary
    extraction_tier: int                 # Which tier succeeded (1-7)
    used_scrapling: bool                 # Whether anti-bot bypass was needed
```

---

## 8. Success Metrics

| Metric | Target | How Measured |
|--------|--------|-------------|
| Content extraction success rate | ≥90% | Fraction of URLs successfully extracted |
| Answer hallucination rate | <5% | Manual audit of citation faithfulness |
| Pipeline latency (median) | <5s | End-to-end from query to answer |
| WAF bypass success rate | ≥95% | Fraction of CF-protected sites successfully scraped |
| Result diversity (MMR) | ≥3 unique domains in top 10 | Domains in top 10 results |
| Query intent accuracy | ≥85% | Manual classification vs. automated |
| Anti-bot detection rate | <5% | Fraction of requests blocked/flagged |

---

## 9. Directory Map

```
browser-goat/
├── src/browser_goat/
│   ├── __init__.py              # Package init, exports BrowserGoat
│   ├── router.py                # Main orchestrator: BrowserGoat.search()
│   ├── models.py                # Pydantic schemas
│   │
│   ├── pre_search/              # Layer 1
│   │   ├── query_intel.py       # Intent, time, entities, complexity
│   │   ├── browser_profiles.py  # 20 profiles, WAF bypass
│   │   └── language_detect.py   # CJK-aware params
│   │
│   ├── post_search/             # Layer 2
│   │   ├── url_pipeline.py      # Normalize, dedup, strip tracking
│   │   └── ranking.py           # RRF + BM25 + MMR
│   │
│   ├── extraction/              # Layer 3 (CORE)
│   │   ├── content_extractor.py # 7-tier cascading
│   │   ├── goal_oriented.py     # Rational/evidence/summary
│   │   └── scrapling_fetcher.py # Anti-bot + CF Turnstile
│   │
│   ├── reliability/             # Layer 4
│   │   ├── give_up_detector.py  # 43 regex patterns
│   │   ├── quality_gate.py      # Retry on insufficient
│   │   └── force_answer.py      # Force synthesis prompt
│   │
│   ├── strategy/                # Layer 5 (Phase 2)
│   │   ├── query_classifier.py
│   │   ├── adaptive_explorer.py
│   │   └── recursive_decomposer.py
│   │
│   └── verification/            # Layer 6 (Phase 3)
│       ├── multi_rollout.py
│       ├── answer_voter.py
│       └── llm_verifier.py
│
├── tests/
│   ├── pre_search/
│   ├── post_search/
│   ├── extraction/
│   └── reliability/
│
├── docs/
│   └── blueprint.md             # THIS FILE
│
├── plans/
│   ├── 01-core-pipeline.md      # Phase 1 implementation plan
│   ├── 02-strategy-intelligence.md  # Phase 2 implementation plan
│   └── 03-verification-scaling.md   # Phase 3 implementation plan
│
├── pyproject.toml
├── opencode.jsonc
├── kilo.json
├── AGENTS.md
├── MEMORY.md
└── README.md
```
