"""Pydantic models for browser-goat data pipeline.

All structured data flowing through the 6-layer pipeline is typed here.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ── Query Analysis ────────────────────────────────────────────────────────────


class QueryIntent(StrEnum):
    """Intent classification for query routing."""

    FACTUAL = "factual"  # "What is the capital of France?"
    TEMPORAL = "temporal"  # "What happened today?"
    PERSON = "person"  # "Who is Satya Nadella?"
    COMPARISON = "comparison"  # "Python vs Rust for web dev"
    HOWTO = "howto"  # "How to deploy a Docker container?"
    RESEARCH = "research"  # "Latest research on quantum computing"


class QueryComplexity(StrEnum):
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"


class QueryAnalysis(BaseModel):
    """Pre-search query intelligence output."""

    intent: QueryIntent
    is_time_sensitive: bool = False
    entities: list[str] = Field(default_factory=list)
    complexity: QueryComplexity = QueryComplexity.MEDIUM
    optimal_sources: int = 15
    news_boost: bool = False


# ── Search Parameters ─────────────────────────────────────────────────────────


class LanguageParams(BaseModel):
    """Language-aware search parameters for SearXNG."""

    location: str = "United States"
    gl: str = "us"  # google language
    hl: str = "en"  # human language


class BrowserProfile(BaseModel):
    """Browser profile for WAF bypass header injection."""

    name: str
    user_agent: str
    sec_ch_ua: str
    sec_ch_ua_platform: str
    sec_ch_ua_mobile: str
    accept: str = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    accept_language: str = "en-US,en;q=0.9"
    accept_encoding: str = "gzip, deflate, br"


class SearxNGSearchParams(BaseModel):
    """Parameters passed to SearXNG search endpoint."""

    query: str
    engines: list[str] = Field(default_factory=lambda: ["google", "bing"])
    categories: list[str] | None = None
    language: str = "en"
    time_range: str | None = None  # day, week, month, year
    pageno: int = 1
    safesearch: int = 0


# ── Search Results Pipeline ────────────────────────────────────────────────────


class RawSearchResult(BaseModel):
    """A single result from SearXNG's JSON API."""

    title: str = ""
    url: str
    content: str = ""  # snippet from SearXNG
    engine: str = ""
    score: float = 0.0
    category: str = ""
    parsed_url: str = ""  # normalized URL
    published_date: str | None = None  # from SearXNG metadata if available


class CleanedResult(RawSearchResult):
    """Result after URL pipeline: normalized, deduped, tracking-param-free."""

    normalized_url: str
    is_duplicate: bool = False
    blocked_reason: str | None = None


class RankedResult(CleanedResult):
    """Result after RRF + BM25 + MMR ranking."""

    rrf_score: float = 0.0
    bm25_score: float = 0.0
    mmr_score: float = 0.0
    final_score: float = 0.0
    rank: int = 0


# ── Extraction Pipeline ────────────────────────────────────────────────────────


class FetchResult(BaseModel):
    """Raw page fetch result from Scrapling or fallback."""

    url: str
    html: str = ""
    status_code: int = 0
    success: bool = False
    error: str | None = None
    used_scrapling: bool = False
    fetch_tier: int = 0  # which escalation tier succeeded (1-6)
    latency_ms: int = 0


class ExtractedContent(BaseModel):
    """Content extracted from a page by the 7-tier extractor."""

    url: str
    title: str = ""
    text: str = ""  # clean article text
    extraction_tier: int = 0  # which tier succeeded (1-7)
    word_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class GoalOrientedResult(ExtractedContent):
    """Content after goal-oriented extraction (rational/evidence/summary)."""

    rational: str = ""  # why this page is relevant to the query
    evidence: str = ""  # specific text passages that answer the query
    summary: str = ""  # condensed 2-3 sentence summary


# ── Reliability Pipeline ───────────────────────────────────────────────────────


class GiveUpResult(BaseModel):
    """Result of give-up detection check."""

    detected: bool = False
    pattern_matched: str | None = None
    language: str = "en"


class QualityResult(BaseModel):
    """Result of quality gate check."""

    passed: bool = True
    reason: str | None = None
    retries_used: int = 0


class ReliabilityInfo(BaseModel):
    """Aggregated reliability metrics for a search."""

    give_up_detected: bool = False
    give_up_pattern: str | None = None
    quality_passed: bool = True
    quality_retries: int = 0
    force_answer_used: bool = False


# ── Final Output ───────────────────────────────────────────────────────────────


class ExtractedSource(BaseModel):
    """A fully processed source ready for the agent."""

    url: str
    title: str
    rational: str
    evidence: str
    summary: str
    extraction_tier: int
    used_scrapling: bool
    rank: int
    final_score: float
    engine: str


class SearchResult(BaseModel):
    """Final output from BrowserGoat.search()."""

    answer: str  # synthesized answer with inline citations
    sources: list[ExtractedSource] = Field(default_factory=list)
    query_intent: QueryIntent = QueryIntent.FACTUAL
    engines_used: list[str] = Field(default_factory=list)
    total_sources_found: int = 0
    total_sources_used: int = 0
    extraction_success_rate: float = 0.0
    pipeline_latency_ms: int = 0
    reliability: ReliabilityInfo = Field(default_factory=ReliabilityInfo)
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class SearchRequest(BaseModel):
    """Input to BrowserGoat.search()."""

    query: str
    engines: list[str] | None = None
    time_range: str | None = None  # day, week, month, year
    language: str = "en"
    max_sources: int = 15
    reliability_mode: str = "standard"  # standard | high | maximum
    strategy: str = "auto"  # auto | default | explore | decompose
    llm_config: dict[str, Any] | None = None  # for goal-oriented extraction


# ── Phase 2: Strategy Layer Models ────────────────────────────────────────────


class ClassificationResult(BaseModel):
    """LLM query classification output for strategy routing."""

    query_type: str = "factual"  # factual, temporal, person, comparison, howto, research, puzzle
    complexity: str = "simple"  # simple, medium, complex
    needs_decomposition: bool = False
    suggested_subtasks: list[str] = Field(default_factory=list)
    confidence: float = 0.5  # 0.0-1.0


class SubTask(BaseModel):
    """A single subtask in recursive decomposition."""

    id: str
    query: str
    dependencies: list[str] = Field(default_factory=list)  # IDs of subtasks this depends on
    status: str = "pending"  # pending, in_progress, completed, failed
    result: str | None = None


class DecomposedResult(BaseModel):
    """Output of recursive query decomposition."""

    subtasks: list[SubTask] = Field(default_factory=list)
    depth: int = 0
    aggregated_answer: str = ""
    intermediate_results: list[SubTask] = Field(default_factory=list)


class StrategyStats(BaseModel):
    """Per-strategy performance tracking for adaptive explorer."""

    strategy_name: str
    attempts: int = 0
    candidates_found: int = 0
    quality_sum: float = 0.0


class ExploreResult(BaseModel):
    """Output of adaptive multi-angle exploration."""

    strategy_stats: list[StrategyStats] = Field(default_factory=list)
    candidates: list[str] = Field(default_factory=list)
    total_attempts: int = 0
    adapted_strategy: str | None = None  # which strategy was promoted after adaptation


# ── Phase 3: Verification Layer Models ────────────────────────────────────────


class ConfidenceLevel(StrEnum):
    """Confidence level for verification results."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


class VoteResult(BaseModel):
    """Output of answer voting across multiple rollouts."""

    consensus: bool = False  # True if a clear winner emerged
    winner_answer: str | None = None
    confidence: ConfidenceLevel = ConfidenceLevel.NONE
    vote_counts: dict[str, int] = Field(default_factory=dict)  # normalized_answer → count
    candidates: list[str] = Field(default_factory=list)  # tied candidates if no consensus


class VerificationResult(BaseModel):
    """Output of LLM verification for tied answers."""

    selected_answer: str = ""
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    reasoning: str = ""
    method: str = "vote"  # vote or llm


class RolloutConfig(BaseModel):
    """Parameter configuration for a single rollout."""

    browser_profile_name: str = "Chrome 147 Windows"
    engines: list[str] = Field(default_factory=lambda: ["google", "bing"])
    time_range: str | None = None
    language: str = "en"


class RolloutResult(BaseModel):
    """Result of a single rollout in multi-rollout verification."""

    config: RolloutConfig = Field(default_factory=RolloutConfig)
    search_result: SearchResult | None = None
    rollout_id: int = 0
