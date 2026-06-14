# Phase 1 — Core Pipeline Implementation Plan

> **Status**: ⏳ Pending | **Target**: Working end-to-end search with Layers 1-4
> **Depends On**: Nothing (this is the foundation)
> **Estimated Effort**: 8-12 days (single developer)

---

## Overview

Phase 1 delivers a working end-to-end product: query → SearXNG → ranked results → extracted content → reliable answer. Layers 5 (Strategy) and 6 (Verification) are deferred to Phases 2 and 3.

### Phase 1 Deliverable

```python
from browsing_meta import BrowsingMeta

meta = BrowsingMeta(searxng_url="http://localhost:8080")
result = await meta.search("What is the latest research on CRISPR?")
# Returns SearchResult with answer, sources (with rational/evidence/summary),
# query intent, latency, and reliability metrics
```

---

## Task Breakdown

### Task 1.0 — Foundation Setup (1 day)

**Goal**: Set up project infrastructure before writing feature code.

| Subtask | File | Effort | Description |
|---------|------|--------|-------------|
| 1.0.1 | `pyproject.toml` | ✓ Done | Dependencies: httpx, bs4, lxml, pydantic, tenacity, tiktoken, playwright, scrapling |
| 1.0.2 | `uv sync` | 10 min | Install all dependencies, verify environment works |
| 1.0.3 | `src/browsing_meta/models.py` | 2 hours | Pydantic schemas: `SearchResult`, `ExtractedSource`, `QueryIntent`, `ReliabilityInfo`, `SearchRequest` |
| 1.0.4 | `src/browsing_meta/searxng_client.py` | 2 hours | Async httpx client for SearXNG JSON API: `search(query, engines, time_range, language) -> list[RawSearchResult]` |
| 1.0.5 | Tests for models + client | 2 hours | Unit tests for serialization, integration test against SearXNG |

**Completion criteria**: Can call SearXNG from Python and get parsed results.

---

### Task 1.1 — Pre-Search Layer (2 days)

**Goal**: Before sending to SearXNG, analyze the query and configure optimal search parameters.

#### Subtask 1.1.1 — Query Intelligence (`pre_search/query_intel.py`)
**Source**: `SearchWala/src/query_intel.rs:71-344`
**Effort**: 4 hours

Port the rule-based query analysis:

```python
class QueryIntent(str, Enum):
    FACTUAL = "factual"        # "What is the capital of France?"
    TEMPORAL = "temporal"      # "What happened today?"
    PERSON = "person"          # "Who is Satya Nadella?"
    COMPARISON = "comparison"  # "Python vs Rust for web dev"
    HOWTO = "howto"            # "How to deploy a Docker container?"
    RESEARCH = "research"      # "Latest research on quantum computing"

@dataclass
class QueryAnalysis:
    intent: QueryIntent
    is_time_sensitive: bool
    entities: list[str]        # Extracted proper nouns
    complexity: str            # "simple" | "medium" | "complex"
    optimal_sources: int       # 10-40 based on complexity
    news_boost: bool            # Boost news engines for temporal queries
```

**Rules to implement** (zero deps, pure pattern matching):
- Intent detection via keyword patterns (regex + category words)
- Time sensitivity via recency keywords ("latest", "recent", "today", "2024", "2025", "2026")
- Entity extraction via capitalized proper noun sequences
- Complexity scoring via word count + entity count + question type

#### Subtask 1.1.2 — Browser Profiles (`pre_search/browser_profiles.py`)
**Source**: `SearchWala/src/config.rs:107-401`
**Effort**: 3 hours

```python
class BrowserProfiles:
    PROFILES = [...]  # 20 profiles: Chrome 147, Edge 147, Firefox 136, Safari 18.4
    
    def get_random_profile(self) -> dict[str, str]:
        """Returns headers dict for one random browser profile."""
    
    def apply_to_request(self, headers: dict) -> dict:
        """Injects Sec-CH-UA, Sec-CH-UA-Platform, Accept-Language, etc."""
```

Each profile includes: User-Agent, Sec-CH-UA, Sec-CH-UA-Platform, Sec-CH-UA-Mobile, Accept, Accept-Language, Accept-Encoding.

#### Subtask 1.1.3 — Language Detection (`pre_search/language_detect.py`)
**Source**: `Tongyi-DeepResearch/inference/tool_search.py:39-56`
**Effort**: 1 hour

```python
def detect_language_params(query: str) -> dict:
    """Returns {location, gl, hl} based on detected language."""
    # If CJK characters detected → location=China, gl=cn, hl=zh-cn
    # Otherwise → location=United States, gl=us, hl=en
```

#### Tests for Layer 1
**Effort**: 4 hours — test each intent type, edge cases (empty query, all-CJK, mixed language)

---

### Task 1.2 — Post-Search Layer (2 days)

**Goal**: After SearXNG returns results, clean and rank them.

#### Subtask 1.2.1 — URL Pipeline (`post_search/url_pipeline.py`)
**Source**: `SearchWala/src/url_utils.rs:98-183`
**Effort**: 3 hours

```python
class URLPipeline:
    TRACKING_PARAMS = ["utm_source", "utm_medium", "utm_campaign", "ref", "fbclid", ...]  # 30+ params
    SKIP_DOMAINS = ["pinterest.com", "quora.com", "facebook.com", ...]  # 15+ domains
    SKIP_EXTENSIONS = [".pdf", ".docx", ".xlsx", ".mp4", ...]  # 14 extensions
    
    def process(self, results: list[RawSearchResult]) -> list[CleanedResult]:
        """Single-pass: normalize URL → check blocklist → strip tracking → dedup."""
```

Key pattern from SearchWala: do everything in ONE pass per URL for efficiency.

#### Subtask 1.2.2 — Hybrid Ranking (`post_search/ranking.py`)
**Source**: `SearchWala/src/ranking.rs:90-533`
**Effort**: 6 hours

```python
class HybridRanker:
    RRF_K = 60        # Cormack 2009
    BM25_DELTA = 1.0  # Lv & Zhai 2011 lower bound
    MMR_LAMBDA = 0.7  # Diversity vs relevance tradeoff
    CHUNK_OVERLAP = 0.15  # 15% sentence overlap
    
    def rank(self, results: list[CleanedResult], query: str) -> list[RankedResult]:
        """Three-stage hybrid ranking pipeline."""
        # Stage A: RRF — cross-engine consensus scoring
        # Stage B: BM25+ — paragraph-level relevance with delta lower bound
        # Stage D: MMR — diversity reranking with Jaccard similarity
```

Implementation details:
- **RRF**: `score = weight / (RRF_K + rank)` — weight comes from engine tiers (Google=1.5, Bing=1.2, others=1.0, aggregators=0.8)
- **BM25+**: `score = BM25(term, chunk) + BM25_DELTA * IDF(term)` — ensures no negative scores
- **MMR**: `score = LAMBDA * relevance - (1-LAMBDA) * max_similarity` — reduces redundancy
- **Chunking**: sentence-boundary-aware, 80-600 chars, 15% overlap, 150 stopwords
- Exact phrase match bonus (+1.25), title match bonus (+0.5/term)

#### Tests for Layer 2
**Effort**: 4 hours — test URL normalization, tracking param stripping, dedup, ranking with known queries

---

### Task 1.3 — Extraction Layer (CORE — 3 days)

**Goal**: Fetch full page content through anti-bot protection, extract clean text, and produce goal-oriented structured summaries.

#### Subtask 1.3.1 — Scrapling Fetcher (`extraction/scrapling_fetcher.py`)
**Source**: Scrapling SKILL.md + `scraper-in-one/src/router.py`
**Effort**: 5 hours

```python
class ScraplingFetcher:
    """Fetch page content with anti-bot bypass, progressive escalation."""
    
    async def fetch(self, url: str, browser_profile: dict) -> FetchResult:
        """
        Tier 1: Scrapling with stealth browser profile (~2s)
        Tier 2: Scrapling with CF Turnstile solving (~5s)
        Tier 3: Scrapling with fresh proxy rotation (~10s)
        Tier 4: Playwright stealth browser (~30s)
        Tier 5: Plain httpx fallback (~1s)
        
        Returns raw HTML or error.
        """
```

Integration point: load Scrapling skill instructions. Use the progressive escalation pattern from `scraper-in-one` — fastest first, escalate only on failure.

#### Subtask 1.3.2 — Content Extractor (`extraction/content_extractor.py`)
**Source**: `SearchWala/src/extractor.rs:143-832`
**Effort**: 8 hours

```python
class ContentExtractor:
    """7-tier cascading content extraction."""
    
    CSS_PATTERNS = [...]  # 35+ CMS-specific selectors
    
    def extract(self, html: str, url: str) -> ExtractedContent:
        """
        Tier 1: JSON-LD extraction (schema.org/Article, NewsArticle, BlogPosting)
        Tier 2: Structured CSS selectors (35+ CMS patterns)
        Tier 3: Semantic HTML5 (article, main, section)
        Tier 4: Scored container (text density score - link penalty)
        Tier 5: Content elements (p, h1-h6 aggregation)
        Tier 6: Meta/og:description fallback
        Tier 7: Full body (last resort)
        
        Returns: title + clean text + metadata + extraction_tier
        """
```

Key implementation details:
- **JSON-LD**: Parse `<script type="application/ld+json">`, extract `articleBody`/`description`
- **Scored container**: `score = len(text) * (1 - links/total_tokens)` — penalizes nav/sidebars
- **Single DOM parse**: Extract title AND text in one BeautifulSoup parse to save 50% overhead
- **Boilerplate filtering**: Regex patterns for "cookie consent", "subscribe to our newsletter", "click here to read more"
- **Paragraph dedup**: Jaccard similarity >0.8 → duplicate → remove

#### Subtask 1.3.3 — Goal-Oriented Extractor (`extraction/goal_oriented.py`)
**Source**: `Tongyi-DeepResearch/inference/tool_visit.py:27-141`
**Effort**: 4 hours

```python
class GoalOrientedExtractor:
    """Produce structured rational/evidence/summary for each extracted page."""
    
    async def extract(self, content: ExtractedContent, query: str, llm_config: dict) -> GoalOrientedResult:
        """
        Uses LLM to produce:
        - rational: Why this page is relevant to the query (1-2 sentences)
        - evidence: Specific text passages that answer the query (2-5 sentences)
        - summary: Condensed 2-3 sentence summary of the page
        
        Token budget: 95K tokens max (truncation if larger)
        Progressive truncation: if LLM fails → truncate to 70% → retry → 25K chars fallback
        """
```

**Prompt template** (from Tongyi):
```
You are a research assistant extracting information from a webpage.

Query: {query}
Page Title: {title}
Page URL: {url}
Page Content: {content}

Extract:
1. RATIONAL: Why is this page relevant to the query?
2. EVIDENCE: What specific information answers the query? Include key facts.
3. SUMMARY: Condensed 1-2 sentence summary of this page's main point.

Format as JSON.
```

#### Tests for Layer 3
**Effort**: 6 hours — test each extraction tier with known HTML fixtures, test Scrapling with Cloudflare-protected sites, test goal-oriented extraction quality

---

### Task 1.4 — Reliability Layer (1.5 days)

**Goal**: Detect when the pipeline produces poor output and recover.

#### Subtask 1.4.1 — Give-Up Detector (`reliability/give_up_detector.py`)
**Source**: `Marco-DeepResearch/marco/agent/context_manager.py:13-45`
**Effort**: 2 hours

```python
class GiveUpDetector:
    # 43 regex patterns (EN + ZH) for agent failure language
    GIVE_UP_PATTERNS_EN = [
        r"I (couldn't|could not|can't|cannot) find",
        r"(no|zero|0) (results|matches|information|data) (found|available)",
        r"unable to (determine|find|locate|identify|answer)",
        r"insufficient (information|data|results|evidence)",
        # ... 20+ more patterns
    ]
    GIVE_UP_PATTERNS_ZH = [
        r"无法(找到|确定|回答)",
        r"没有(找到|发现|相关)",
        # ... 10+ more patterns
    ]
    
    def detect(self, text: str) -> bool:
        """Returns True if text matches any give-up pattern."""
```

#### Subtask 1.4.2 — Quality Gate (`reliability/quality_gate.py`)
**Source**: `SearchWala/src/llm.rs:1678-1700`
**Effort**: 2 hours

```python
class QualityGate:
    MIN_ANSWER_LENGTH = 80  # chars
    MAX_RETRIES = 1
    
    def check(self, answer: str, sources: list[ExtractedSource]) -> QualityResult:
        """Check if answer meets quality thresholds."""
        if len(answer) < self.MIN_ANSWER_LENGTH:
            return QualityResult(passed=False, reason="answer_too_short")
        if not any(source.evidence for source in sources):
            return QualityResult(passed=False, reason="no_citations")
        return QualityResult(passed=True)
```

#### Subtask 1.4.3 — Force Answer (`reliability/force_answer.py`)
**Source**: `Marco-DeepResearch/marco/prompts/inference.py:57-70`
**Effort**: 1 hour

```python
FORCE_ANSWER_PROMPT = """You have reached the limit of your search. 
Based on the information gathered so far, provide your best answer.
If truly insufficient, state what's missing and suggest next steps.
Include all available citations.

Sources:
{sources}

Query: {query}

Your answer:"""
```

#### Tests for Layer 4
**Effort**: 3 hours — test each give-up pattern against known failure messages, test quality gate thresholds

---

### Task 1.5 — Router Integration (1.5 days)

**Goal**: Wire all layers together into a single `BrowsingMeta.search()` call.

#### Subtask 1.5.1 — Main Router (`src/browsing_meta/router.py`)
**Effort**: 6 hours

```python
class BrowsingMeta:
    def __init__(self, searxng_url: str, llm_config: dict | None = None):
        self.searxng = SearXNGClient(searxng_url)
        self.query_intel = QueryIntel()
        self.browser_profiles = BrowserProfiles()
        self.url_pipeline = URLPipeline()
        self.ranker = HybridRanker()
        self.content_extractor = ContentExtractor()
        self.goal_extractor = GoalOrientedExtractor(llm_config)
        self.scrapling = ScraplingFetcher()
        self.give_up = GiveUpDetector()
        self.quality = QualityGate()
    
    async def search(self, query: str) -> SearchResult:
        """End-to-end: query → SearXNG → ranked → extracted → reliable answer."""
        # Layer 1: Pre-Search
        analysis = self.query_intel.analyze(query)
        lang_params = detect_language_params(query)
        profile = self.browser_profiles.get_random_profile()
        enriched_query = self._enrich_query(query, analysis)
        
        # Layer 2: SearXNG + Post-Search
        raw_results = await self.searxng.search(enriched_query, ...)
        cleaned = self.url_pipeline.process(raw_results)
        ranked = self.ranker.rank(cleaned, query)
        
        # Layer 3: Extraction
        extracted = await self._extract_all(ranked[:15], profile, query)
        
        # Layer 4: Reliability
        answer = self._synthesize_answer(extracted, query)
        if self.give_up.detect(answer):
            answer = self._force_answer(extracted, query)
        if not self.quality.check(answer, extracted).passed:
            answer = self._retry_synthesis(extracted, query)
        
        return SearchResult(...)
```

Key design decisions:
- Extract top 15 (after ranking), not all results
- Concurrency: 8 workers for extraction (semaphore)
- Timeout: 30s total, 15s per page fetch
- Progressive: extract content first, THEN goal-oriented (content can be cached)

#### Subtask 1.5.2 — Integration Test
**Effort**: 4 hours

End-to-end test with real SearXNG:
1. Query: "What is the capital of France?"
2. Verify: intent=factual, answer contains "Paris", sources include Wikipedia
3. Query: "Latest developments in quantum computing 2026"
4. Verify: intent=research, time_sensitive=true, sources are recent
5. Query: "Python vs Rust for web development"
6. Verify: intent=comparison, answer compares both

#### Tests for Router
**Effort**: 4 hours — integration tests, error handling (SearXNG down, all extraction fails, empty results)

---

### Task 1.6 — Quality Gate (0.5 day)

**Effort**: 2 hours

```bash
uv run ruff check src/ tests/    # Zero violations
uv run mypy src/                  # Zero errors
uv run pytest                     # All pass, ≥80% coverage
```

Fix any issues, ensure all type hints are complete.

---

## Phase 1 Completion Criteria

- [ ] `BrowsingMeta.search("query")` returns a complete `SearchResult`
- [ ] Query intelligence correctly classifies all 6 intent types
- [ ] Browser profiles rotate randomly and inject correct headers
- [ ] URL pipeline strips tracking params from known URLs
- [ ] RRF ranking weights Google results higher than aggregators
- [ ] Content extraction succeeds on at least Tier 4 for most pages
- [ ] Scrapling successfully fetches Cloudflare-protected pages
- [ ] Goal-oriented extraction produces structured rational/evidence/summary
- [ ] Give-up detector catches "I couldn't find" language
- [ ] Quality gate retries on short/missing-citation answers
- [ ] All tests pass, typecheck clean, lint clean
- [ ] End-to-end latency <10s for typical queries

---

## Task Dependency Graph

```
1.0 Foundation ────┬── 1.1 Pre-Search ────┬── 1.5 Router
                   │                      │
                   ├── 1.2 Post-Search ───┤
                   │                      │
                   ├── 1.3 Extraction ────┤
                   │                      │
                   └── 1.4 Reliability ───┘

1.6 Quality Gate ← after 1.5
```

Tasks 1.1-1.4 can be developed in parallel after 1.0 is complete.
