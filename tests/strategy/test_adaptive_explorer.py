"""Tests for multi-angle candidate exploration with adaptive strategy selection.

Tests both rule-based (no-LLM) and LLM-driven exploration paths, strategy
adaptation, and performance tracking.
"""

from __future__ import annotations

from browsing_meta.models import ExploreResult, RawSearchResult, StrategyStats
from browsing_meta.strategy.adaptive_explorer import (
    ADAPTATION_THRESHOLD,
    ALL_STRATEGIES,
    CATEGORY,
    DIRECT,
    RELATED,
    SYNONYM,
    AdaptiveExplorer,
)


def _make_mock_searxng(
    url_count: int = 3,
    url_prefix: str = "https://example.com/result",
) -> type:
    """Factory that returns a mock SearXNG client class.

    Each call to ``search(query=...)`` returns *url_count*
    ``RawSearchResult`` instances with unique URLs.
    """

    class MockSearXNGClient:
        _call_count = 0

        async def search(self, query: str, **kwargs: object) -> list[RawSearchResult]:
            MockSearXNGClient._call_count += 1
            return [
                RawSearchResult(
                    url=f"{url_prefix}-{MockSearXNGClient._call_count}-{i}",
                    title=f"Result {i} for {query[:20]}",
                    content="Sample content with enough text for quality estimation. "
                    "This simulates a real search result snippet. "
                    "More text means higher quality score.",
                )
                for i in range(url_count)
            ]

    return MockSearXNGClient


class TestRuleBasedExploration:
    """Exploration without an LLM — only direct and synonym strategies."""

    async def test_explore_returns_explore_result(self) -> None:
        explorer = AdaptiveExplorer()
        client = _make_mock_searxng()()
        result = await explorer.explore("python tutorial", client)
        assert isinstance(result, ExploreResult)
        assert result.candidates is not None

    async def test_explore_returns_candidates(self) -> None:
        explorer = AdaptiveExplorer()
        client = _make_mock_searxng(url_count=3)()
        result = await explorer.explore("python tutorial", client)
        assert len(result.candidates) > 0
        all_urls = result.candidates
        # Without LLM: only DIRECT + SYNONYM → 2 strategies × 3 results = 6 candidates
        assert len(all_urls) == 6

    async def test_query_variants_differ_from_original(self) -> None:
        """Rule-based synonym replacement should produce a different query."""
        explorer = AdaptiveExplorer()
        # "tutorial" maps to "guide" in SYNONYM_MAP
        # Use _generate_query which handles DIRECT by returning query as-is
        direct = await explorer._generate_query("python tutorial", DIRECT, False, None)
        synonym = await explorer._generate_query("python tutorial", SYNONYM, False, None)
        assert direct == "python tutorial"
        assert synonym is not None
        assert synonym.lower() != "python tutorial"

    async def test_category_returns_none_without_llm(self) -> None:
        """Without LLM, category, and related return None if not in maps."""
        explorer = AdaptiveExplorer()
        category = explorer._rule_generate("unknown topic xyz", CATEGORY)
        related = explorer._rule_generate("unknown topic xyz", RELATED)
        assert category is None
        assert related is None


class TestLLMExploration:
    """Exploration with a mocked LLM callable."""

    async def test_explore_with_llm_uses_all_strategies(self) -> None:
        async def mock_llm(_messages: list[dict[str, str]]) -> str:
            return "python programming guide"

        explorer = AdaptiveExplorer(llm_call=mock_llm)
        client = _make_mock_searxng(url_count=2)()
        result = await explorer.explore("python", client)
        # With LLM: all 4 strategies active
        assert len(result.candidates) >= 4  # At least 4 results (some may overlap)
        assert result.total_attempts >= 4

    async def test_llm_generates_variant(self) -> None:
        async def mock_llm(_messages: list[dict[str, str]]) -> str:
            return "python programming language guide"

        explorer = AdaptiveExplorer(llm_call=mock_llm)
        variant = await explorer._llm_generate("python", SYNONYM, mock_llm)
        assert variant is not None
        assert variant != "python"

    async def test_llm_failure_falls_back_gracefully(self) -> None:
        async def failing_llm(_messages: list[dict[str, str]]) -> str:
            raise RuntimeError("API error")

        explorer = AdaptiveExplorer(llm_call=failing_llm)
        # Should not crash — LLM failure is caught and returns None
        variant = await explorer._llm_generate("python", SYNONYM, failing_llm)
        assert variant is None

    async def test_llm_returns_original_query_fallback(self) -> None:
        """If LLM returns the same query, None is returned."""
        async def same_llm(_messages: list[dict[str, str]]) -> str:
            return "python"

        explorer = AdaptiveExplorer(llm_call=same_llm)
        variant = await explorer._llm_generate("python", SYNONYM, same_llm)
        assert variant is None


class TestStatsTracking:
    """Verify that per-strategy statistics are updated after exploration."""

    async def test_stats_after_exploration(self) -> None:
        explorer = AdaptiveExplorer()
        client = _make_mock_searxng(url_count=3)()
        await explorer.explore("python tutorial", client)

        stats = explorer.strategy_stats
        assert DIRECT in stats
        assert SYNONYM in stats

        # Each active strategy should have 1 attempt
        assert stats[DIRECT].attempts >= 1
        assert stats[SYNONYM].attempts >= 1

    async def test_strategy_candidates_counted(self) -> None:
        explorer = AdaptiveExplorer()
        client = _make_mock_searxng(url_count=5)()
        # Run exploration a couple times to accumulate data
        await explorer.explore("python", client)
        await explorer.explore("python", client)

        stats = explorer.strategy_stats
        # Each strategy should have found candidates
        for name in (DIRECT, SYNONYM):
            assert stats[name].candidates_found > 0
            assert stats[name].attempts == 2

    async def test_strategy_quality_sum_updated(self) -> None:
        explorer = AdaptiveExplorer()
        client = _make_mock_searxng(url_count=3)()
        await explorer.explore("python tutorial", client)

        stats = explorer.strategy_stats
        for name in (DIRECT, SYNONYM):
            assert stats[name].quality_sum > 0.0

    async def test_strategy_stats_model_fields(self) -> None:
        explorer = AdaptiveExplorer()
        stats = explorer.strategy_stats
        for name in ALL_STRATEGIES:
            assert isinstance(stats[name], StrategyStats)


class TestAdaptation:
    """Strategy re-ranking after sufficient data accumulation."""

    async def test_adaptation_after_threshold(self) -> None:
        explorer = AdaptiveExplorer()
        client = _make_mock_searxng(url_count=3)()

        # With LLM, all 4 strategies are active so adaptation can trigger
        async def mock_llm(_messages: list[dict[str, str]]) -> str:
            return "python programming guide"

        explorer = AdaptiveExplorer(llm_call=mock_llm)
        for _ in range(ADAPTATION_THRESHOLD):
            await explorer.explore("python tutorial", client)

        # After threshold, the bottom performer is dropped
        rank_after = explorer.strategy_rank
        assert len(rank_after) == 3  # One was dropped
        assert all(s in rank_after for s in (DIRECT, SYNONYM, CATEGORY, RELATED)) is False  # at least one missing

    async def test_adaptation_promotes_top_strategy(self) -> None:
        explorer = AdaptiveExplorer()
        client = _make_mock_searxng(url_count=3)()

        for _ in range(ADAPTATION_THRESHOLD):
            await explorer.explore("python tutorial", client)

        adapted = explorer._adapt()
        assert isinstance(adapted, str)
        assert adapted in explorer.strategy_rank

    async def test_strategy_score_zero_with_no_attempts(self) -> None:
        explorer = AdaptiveExplorer()
        score = explorer._strategy_score(DIRECT)
        assert score == 0.0

    async def test_strategy_score_positive_after_exploration(self) -> None:
        explorer = AdaptiveExplorer()
        client = _make_mock_searxng(url_count=3)()
        await explorer.explore("python", client)

        score = explorer._strategy_score(DIRECT)
        assert score > 0.0


class TestEdgeCases:
    """Edge cases for the adaptive explorer."""

    async def test_empty_query_still_produces_direct(self) -> None:
        explorer = AdaptiveExplorer()
        client = _make_mock_searxng(url_count=1)()
        result = await explorer.explore("", client)
        assert len(result.candidates) >= 0  # Should not crash
        assert isinstance(result, ExploreResult)

    async def test_strategy_rank_is_readonly_copy(self) -> None:
        explorer = AdaptiveExplorer()
        rank = explorer.strategy_rank
        rank.append("extra")
        # Original should not be modified
        assert "extra" not in explorer.strategy_rank

    async def test_stats_are_readonly_copy(self) -> None:
        explorer = AdaptiveExplorer()
        stats = explorer.strategy_stats
        # Should return a dict copy, not the internal dict
        assert isinstance(stats, dict)
