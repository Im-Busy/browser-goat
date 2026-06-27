"""Tests for multi-rollout verification."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from browser_goat.models import RolloutConfig, SearchResult
from browser_goat.verification.multi_rollout import MultiRollout


class TestGenerateConfigs:
    def test_returns_correct_number(self) -> None:
        configs = MultiRollout._generate_configs(3)
        assert len(configs) == 3

    def test_each_config_has_varied_parameters(self) -> None:
        configs = MultiRollout._generate_configs(5)
        names = [c.browser_profile_name for c in configs]
        assert len(set(names)) == 5

    def test_configs_cycle_through_engines_with_60_rollouts(self) -> None:
        """Engine subsets cycle after every 20 profiles."""
        configs = MultiRollout._generate_configs(60)
        engine_sets = {tuple(c.engines) for c in configs}
        assert len(engine_sets) == 3  # google+bing, google+scholar, bing+scholar

    def test_generates_up_to_max_rollouts(self) -> None:
        configs = MultiRollout._generate_configs(MultiRollout.MAX_ROLLOUTS)
        assert len(configs) == MultiRollout.MAX_ROLLOUTS

    def test_each_config_is_rollout_config(self) -> None:
        configs = MultiRollout._generate_configs(3)
        for c in configs:
            assert isinstance(c, RolloutConfig)

    def test_configs_cycle_through_time_ranges(self) -> None:
        configs = MultiRollout._generate_configs(121)
        time_ranges = {c.time_range for c in configs}
        assert None in time_ranges
        assert "month" in time_ranges
        assert "year" in time_ranges


class TestExtractAnswer:
    def test_extracts_answer_string(self) -> None:
        result = SearchResult(answer="Paris is the capital of France.")
        assert MultiRollout._extract_answer(result) == "Paris is the capital of France."

    def test_extracts_empty_answer(self) -> None:
        result = SearchResult(answer="")
        assert MultiRollout._extract_answer(result) == ""


class TestExecute:
    @pytest.fixture
    def mock_meta(self) -> MagicMock:
        """Create a mock BrowserGoat-like object with async search()."""
        meta = MagicMock()
        meta.search = AsyncMock()
        return meta

    @pytest.mark.asyncio
    async def test_single_rollout_returns_one_result(self, mock_meta: MagicMock) -> None:
        mock_meta.search.return_value = SearchResult(answer="42 is the answer.")
        mr = MultiRollout()
        results = await mr.execute("meaning of life", meta=mock_meta, num_rollouts=1)
        assert len(results) == 1
        assert results[0].answer == "42 is the answer."

    @pytest.mark.asyncio
    async def test_multiple_rollouts_return_multiple_results(self, mock_meta: MagicMock) -> None:
        mock_meta.search.side_effect = [
            SearchResult(answer="Result A"),
            SearchResult(answer="Result B"),
            SearchResult(answer="Result C"),
        ]
        mr = MultiRollout()
        results = await mr.execute("test query", meta=mock_meta, num_rollouts=3)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_rollout_passes_different_params_to_meta(self, mock_meta: MagicMock) -> None:
        """Verify each rollout call receives different engine/time/query params."""
        captured: list[dict[str, object]] = []

        async def capture(**kwargs: object) -> SearchResult:
            captured.append(kwargs)
            return SearchResult(answer=f"result {len(captured)}")

        mock_meta.search.side_effect = capture
        mr = MultiRollout()
        await mr.execute("what is the meaning of life", meta=mock_meta, num_rollouts=3)
        assert len(captured) == 3
        # First rollout uses the original query
        assert captured[0]["query"] == "what is the meaning of life"
        # Queries vary across rollouts (at least one is different)
        queries = [c["query"] for c in captured]
        assert len(set(queries)) > 1

    @pytest.mark.asyncio
    async def test_num_rollouts_clamped_to_max(self, mock_meta: MagicMock) -> None:
        mock_meta.search.return_value = SearchResult(answer="test")
        mr = MultiRollout()
        results = await mr.execute("test", meta=mock_meta, num_rollouts=100)
        assert len(results) <= MultiRollout.MAX_ROLLOUTS

    @pytest.mark.asyncio
    async def test_num_rollouts_minimum_is_one(self, mock_meta: MagicMock) -> None:
        mock_meta.search.return_value = SearchResult(answer="test")
        mr = MultiRollout()
        results = await mr.execute("test", meta=mock_meta, num_rollouts=0)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_individual_rollout_failure_skipped(self, mock_meta: MagicMock) -> None:
        """A single failing rollout should not crash the whole operation."""
        call_count = 0

        async def fail_on_second_call(**kwargs: object) -> SearchResult:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("Search failed")
            return SearchResult(answer="result")

        mock_meta.search.side_effect = fail_on_second_call
        mr = MultiRollout()
        results = await mr.execute("test", meta=mock_meta, num_rollouts=3)
        assert len(results) == 2  # one failed, two succeeded

    @pytest.mark.asyncio
    async def test_early_stop_when_consensus_reached(self, mock_meta: MagicMock) -> None:
        """When 4+ identical answers emerge, remaining rollouts should be cancelled."""
        call_count = 0

        async def delayed_result(**kwargs: object) -> SearchResult:
            nonlocal call_count
            call_count += 1
            if call_count <= 5:
                return SearchResult(answer="Consensus answer")
            await asyncio.sleep(0.5)
            return SearchResult(answer="Consensus answer")

        mock_meta.search.side_effect = delayed_result
        mr = MultiRollout()
        results = await mr.execute(
            "test", meta=mock_meta, num_rollouts=MultiRollout.MAX_ROLLOUTS
        )
        assert len(results) >= MultiRollout.EARLY_STOP_THRESHOLD
        assert len(results) < MultiRollout.MAX_ROLLOUTS
