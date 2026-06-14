"""Tests for BrowsingMeta router — main search orchestrator.

ALL tests mock SearXNG and external services — no real HTTP calls.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from browsing_meta.models import (
    ClassificationResult,
    ConfidenceLevel,
    ExtractedSource,
    RawSearchResult,
    SearchResult,
    VoteResult,
)
from browsing_meta.router import BrowsingMeta
from browsing_meta.verification.multi_rollout import MultiRollout

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_raw_results() -> list[RawSearchResult]:
    """Controlled SearXNG results for use across tests."""
    return [
        RawSearchResult(
            title="Python Programming Language",
            url="https://python.org",
            content="Python is a high-level programming language.",
            engine="google",
            score=0.95,
            category="general",
        ),
        RawSearchResult(
            title="Python Documentation",
            url="https://docs.python.org",
            content="Official Python documentation and tutorials.",
            engine="bing",
            score=0.85,
            category="general",
        ),
        RawSearchResult(
            title="Learn Python",
            url="https://example.com/learn-python",
            content="A beginner-friendly guide to learning Python.",
            engine="google",
            score=0.75,
            category="general",
        ),
    ]


@pytest.fixture
def mock_sources() -> list[ExtractedSource]:
    """Controlled extracted sources for the mock extraction pipeline."""
    return [
        ExtractedSource(
            url="https://python.org",
            title="Python Programming Language",
            rational="Official Python site with language details.",
            evidence="Python is a high-level, interpreted programming language.",
            summary="Python is a versatile programming language.",
            extraction_tier=2,
            used_scrapling=False,
            rank=1,
            final_score=0.95,
            engine="google",
        ),
        ExtractedSource(
            url="https://docs.python.org",
            title="Python Documentation",
            rational="Comprehensive documentation for Python.",
            evidence="Official docs covering all Python features.",
            summary="Python docs are extensive and well-maintained.",
            extraction_tier=2,
            used_scrapling=False,
            rank=2,
            final_score=0.85,
            engine="bing",
        ),
    ]


# ── Initialization ────────────────────────────────────────────────────────────


class TestInit:
    def test_creates_all_sub_components(self) -> None:
        """BrowsingMeta() instantiates every sub-component."""
        meta = BrowsingMeta(searxng_url="http://mock-searxng:8080")

        # Pre-Search
        assert meta.searxng is not None
        assert meta.query_intel is not None
        assert meta.browser_profiles is not None

        # Post-Search
        assert meta.url_pipeline is not None
        assert meta.ranker is not None

        # Extraction
        assert meta.content_extractor is not None
        assert meta.goal_extractor is not None
        assert meta.scrapling is not None

        # Reliability
        assert meta.give_up is not None
        assert meta.quality is not None

        # Phase 2 — Strategy
        assert meta.query_classifier is not None
        assert meta.adaptive_explorer is not None
        assert meta.recursive_decomposer is not None

        # Phase 3 — Verification
        assert meta.multi_rollout is not None
        assert meta.answer_voter is not None
        assert meta.llm_verifier is not None


# ── Default Search Pipeline ───────────────────────────────────────────────────


class TestDefaultSearch:
    """Tests for the Phase 1 default pipeline path."""

    @patch.object(BrowsingMeta, "_extract_sources")
    async def test_search_returns_search_result(
        self,
        mock_extract: AsyncMock,
        mock_raw_results: list[RawSearchResult],
        mock_sources: list[ExtractedSource],
    ) -> None:
        """search() with default params returns SearchResult with correct fields."""
        mock_extract.return_value = (mock_sources, mock_sources, 1.0)

        meta = BrowsingMeta(searxng_url="http://mock-searxng:8080")

        with patch.object(meta.searxng, "search", new=AsyncMock(return_value=mock_raw_results)):
            result = await meta.search(query="What is Python?")

        assert isinstance(result, SearchResult)
        assert result.answer
        assert "Python" in result.answer
        assert len(result.sources) == 2
        assert result.sources[0].url == "https://python.org"
        assert result.query_intent.value == "factual"
        assert result.total_sources_found == 3
        assert result.extraction_success_rate == 1.0
        assert result.pipeline_latency_ms >= 0
        assert result.engines_used is not None

    @patch.object(BrowsingMeta, "_extract_sources")
    async def test_search_custom_engines(
        self,
        mock_extract: AsyncMock,
        mock_raw_results: list[RawSearchResult],
        mock_sources: list[ExtractedSource],
    ) -> None:
        """Custom engines list is passed through to SearXNG."""
        mock_extract.return_value = (mock_sources, mock_sources, 1.0)

        meta = BrowsingMeta(searxng_url="http://mock-searxng:8080")
        custom_engines = ["brave", "duckduckgo"]

        with patch.object(meta.searxng, "search", new=AsyncMock(return_value=mock_raw_results)) as mock_search:
            result = await meta.search(query="Python", engines=custom_engines)

        # Verify the engines were passed to SearXNG
        call_kwargs = mock_search.call_args.kwargs
        assert call_kwargs["engines"] == custom_engines
        assert result.engines_used == custom_engines

    @patch.object(BrowsingMeta, "_extract_sources")
    async def test_search_with_time_range(
        self,
        mock_extract: AsyncMock,
        mock_raw_results: list[RawSearchResult],
        mock_sources: list[ExtractedSource],
    ) -> None:
        """time_range parameter flows through to SearXNG."""
        mock_extract.return_value = (mock_sources, mock_sources, 1.0)

        meta = BrowsingMeta(searxng_url="http://mock-searxng:8080")

        with patch.object(meta.searxng, "search", new=AsyncMock(return_value=mock_raw_results)) as mock_search:
            await meta.search(query="Python news", time_range="week")

        call_kwargs = mock_search.call_args.kwargs
        assert call_kwargs["time_range"] == "week"

    @patch.object(BrowsingMeta, "_extract_sources")
    async def test_search_empty_results_graceful(
        self,
        mock_extract: AsyncMock,
    ) -> None:
        """Empty results from SearXNG are handled gracefully."""
        mock_extract.return_value = ([], [], 0.0)

        meta = BrowsingMeta(searxng_url="http://mock-searxng:8080")

        with patch.object(meta.searxng, "search", new=AsyncMock(return_value=[])):
            result = await meta.search(query="xyznonexistent12345")

        assert isinstance(result, SearchResult)
        assert result.total_sources_found == 0
        assert result.total_sources_used == 0
        assert result.sources == []
        assert "No relevant information" in result.answer


# ── Strategy: "auto" ──────────────────────────────────────────────────────────


class TestStrategyAuto:
    """Tests for the strategy='auto' path."""

    @patch.object(BrowsingMeta, "_extract_sources")
    async def test_auto_calls_query_classifier(
        self,
        mock_extract: AsyncMock,
        mock_raw_results: list[RawSearchResult],
        mock_sources: list[ExtractedSource],
    ) -> None:
        """strategy='auto' invokes the query classifier."""
        mock_extract.return_value = (mock_sources, mock_sources, 1.0)

        meta = BrowsingMeta(searxng_url="http://mock-searxng:8080")
        # Classification says "research" → should route to explore path
        mock_classify = AsyncMock(
            return_value=ClassificationResult(
                query_type="research",
                complexity="complex",
                needs_decomposition=True,
                suggested_subtasks=["Find papers", "Summarize"],
                confidence=0.85,
            )
        )

        with (
            patch.object(meta.searxng, "search", new=AsyncMock(return_value=mock_raw_results)),
            patch.object(meta.query_classifier, "classify", new=mock_classify),
        ):
            result = await meta.search(query="Latest AI research", strategy="auto")

        mock_classify.assert_called_once_with("Latest AI research")
        assert isinstance(result, SearchResult)
        assert len(result.sources) == 2


# ── Strategy: "decompose" ─────────────────────────────────────────────────────


class TestStrategyDecompose:
    """Tests for the strategy='decompose' path."""

    @patch.object(BrowsingMeta, "_extract_sources")
    async def test_decompose_calls_recursive_decomposer(
        self,
        mock_extract: AsyncMock,
        mock_raw_results: list[RawSearchResult],
        mock_sources: list[ExtractedSource],
    ) -> None:
        """strategy='decompose' calls recursive_decomposer.decompose_and_solve."""
        mock_extract.return_value = (mock_sources, mock_sources, 1.0)

        meta = BrowsingMeta(searxng_url="http://mock-searxng:8080")

        with patch.object(meta.searxng, "search", new=AsyncMock(return_value=mock_raw_results)):
            result = await meta.search(
                query="What are the differences between Python and Rust?",
                strategy="decompose",
            )

        assert isinstance(result, SearchResult)
        assert len(result.sources) == 2
        # decompose path runs a SearXNG search internally
        assert result.total_sources_found == 3


# ── Reliability: "high" ───────────────────────────────────────────────────────


class TestReliabilityHigh:
    """Tests for the reliability_mode='high' path."""

    async def test_high_calls_multi_rollout_and_answer_voter(
        self,
        mock_sources: list[ExtractedSource],
    ) -> None:
        """reliability_mode='high' triggers multi_rollout.execute and answer_voter.vote."""
        consensus_result = SearchResult(
            answer="Python is a programming language.",
            sources=mock_sources,
            query_intent="factual",
            engines_used=["google", "bing"],
            total_sources_found=2,
            total_sources_used=2,
            extraction_success_rate=1.0,
            pipeline_latency_ms=100,
        )

        meta = BrowsingMeta(searxng_url="http://mock-searxng:8080")

        mock_vote = VoteResult(
            consensus=True,
            winner_answer="Python is a programming language.",
            confidence=ConfidenceLevel.HIGH,
            vote_counts={
                "python is a programming language.": 5,
            },
            candidates=[],
        )

        with (
            patch.object(MultiRollout, "execute", new=AsyncMock(return_value=[consensus_result] * 5)),
            patch.object(meta.answer_voter, "vote", return_value=mock_vote),
        ):
            result = await meta.search(
                query="What is Python?",
                reliability_mode="high",
            )

        assert result.answer == "Python is a programming language."
        assert result.query_intent == "factual"


# ── _enrich_query ─────────────────────────────────────────────────────────────


class TestEnrichQuery:
    """Tests for the query enrichment logic inside the default pipeline."""

    @patch.object(BrowsingMeta, "_extract_sources")
    async def test_enrich_query_adds_year_for_time_sensitive(
        self,
        mock_extract: AsyncMock,
        mock_raw_results: list[RawSearchResult],
        mock_sources: list[ExtractedSource],
    ) -> None:
        """Time-sensitive queries get a year appended via query_intel.enrich_query."""
        mock_extract.return_value = (mock_sources, mock_sources, 1.0)

        meta = BrowsingMeta(searxng_url="http://mock-searxng:8080")

        with patch.object(meta.searxng, "search", new=AsyncMock(return_value=mock_raw_results)) as mock_search:
            await meta.search(query="latest Python releases")

        # Verify the enriched query (with year) was sent to SearXNG
        call_args = mock_search.call_args
        sent_query = call_args.kwargs.get("query") or call_args.args[0]
        assert "2026" in sent_query

    @patch.object(BrowsingMeta, "_extract_sources")
    async def test_enrich_query_no_duplicate_year(
        self,
        mock_extract: AsyncMock,
        mock_raw_results: list[RawSearchResult],
        mock_sources: list[ExtractedSource],
    ) -> None:
        """Queries already containing a year don't get a duplicate appended."""
        mock_extract.return_value = (mock_sources, mock_sources, 1.0)

        meta = BrowsingMeta(searxng_url="http://mock-searxng:8080")
        query_with_year = "Python developments 2026"

        with patch.object(meta.searxng, "search", new=AsyncMock(return_value=mock_raw_results)) as mock_search:
            await meta.search(query=query_with_year)

        call_args = mock_search.call_args
        sent_query = call_args.kwargs.get("query") or call_args.args[0]
        # The query should only have one instance of "2026"
        assert sent_query.count("2026") == 1
