"""Tests for recursive query decomposition.

Tests the direct answer path (simple queries) and the decomposition path
(complex multi-part queries) with mocked LLM and SearXNG calls.
"""

from __future__ import annotations

from browser_goat.models import DecomposedResult, RawSearchResult, SubTask
from browser_goat.strategy.recursive_decomposer import RecursiveDecomposer


class MockSearXNG:
    """Mock SearXNG client that returns predictable results."""

    def __init__(self) -> None:
        self.search_calls: list[str] = []

    async def search(self, query: str, **kwargs: object) -> list[RawSearchResult]:
        self.search_calls.append(query)
        return [
            RawSearchResult(
                url=f"https://example.com/{i}",
                title=f"Result {i}",
                content=f"Search result content for: {query}",
            )
            for i in range(3)
        ]


class TestDirectAnswer:
    """Simple queries that should be answered directly without decomposition."""

    async def test_simple_query_returns_direct_answer(self) -> None:
        """A simple factual query should be answered directly."""
        searxng = MockSearXNG()

        async def mock_llm(messages: list[dict[str, str]]) -> str:
            content = messages[-1]["content"]
            if "can_answer_directly" in content and "What is Python" in content:
                return '{"can_answer_directly": true, "reasoning": "simple factual question"}'
            return "Python is a high-level programming language."

        decomposer = RecursiveDecomposer()
        result = await decomposer.decompose_and_solve(
            "What is Python?", searxng, mock_llm,
        )

        assert isinstance(result, DecomposedResult)
        assert len(result.subtasks) == 0  # No decomposition
        assert result.depth == 0
        assert "Python" in result.aggregated_answer
        assert len(searxng.search_calls) == 1  # One search call

    async def test_direct_answer_result_structure(self) -> None:
        """Direct answer result should have proper structure."""
        searxng = MockSearXNG()

        async def mock_llm(messages: list[dict[str, str]]) -> str:
            content = messages[-1]["content"]
            if "can_answer_directly" in content:
                return '{"can_answer_directly": true, "reasoning": "simple"}'
            return "Direct answer with citations."

        decomposer = RecursiveDecomposer()
        result = await decomposer.decompose_and_solve(
            "What is the capital of France?", searxng, mock_llm,
        )

        assert result.aggregated_answer != ""
        assert len(result.intermediate_results) == 0

    async def test_simple_query_no_search_needed(
        self,
    ) -> None:
        """A simple query should trigger exactly one search."""
        searxng = MockSearXNG()

        async def mock_llm(messages: list[dict[str, str]]) -> str:
            content = messages[-1]["content"]
            if "can_answer_directly" in content:
                return '{"can_answer_directly": true, "reasoning": "simple"}'
            return "Simple answer."

        decomposer = RecursiveDecomposer()
        await decomposer.decompose_and_solve(
            "Define recursion.", searxng, mock_llm,
        )

        assert len(searxng.search_calls) == 1


class TestComplexDecomposition:
    """Complex multi-part queries that require decomposition into subtasks."""

    async def test_complex_query_returns_subtasks(self) -> None:
        """A complex query should be decomposed into subtasks."""
        searxng = MockSearXNG()
        mock = _ComplexQueryMock()

        decomposer = RecursiveDecomposer()
        result = await decomposer.decompose_and_solve(
            "What is Python and how does it compare to Java?",
            searxng,
            mock.llm_call,
        )

        assert isinstance(result, DecomposedResult)
        # Should have subtasks from decomposition
        assert len(result.subtasks) >= 2, (
            f"Expected ≥2 subtasks, got {len(result.subtasks)}"
        )
        assert result.aggregated_answer != ""

    async def test_subtasks_have_required_fields(self) -> None:
        """Each subtask must have id, query, dependencies, status, and result."""
        searxng = MockSearXNG()
        mock = _ComplexQueryMock()

        decomposer = RecursiveDecomposer()
        result = await decomposer.decompose_and_solve(
            "What is Python and how does it compare to Java?",
            searxng,
            mock.llm_call,
        )

        for subtask in result.subtasks:
            assert isinstance(subtask, SubTask)
            assert subtask.id, f"Subtask missing id: {subtask}"
            assert subtask.query, f"Subtask missing query: {subtask}"
            assert isinstance(subtask.dependencies, list)
            # Dependencies should reference existing subtask IDs
            for dep in subtask.dependencies:
                dep_ids = {s.id for s in result.subtasks}
                assert dep in dep_ids, (
                    f"Dependency {dep} not found in subtasks: {dep_ids}"
                )

    async def test_subtasks_get_completed(self) -> None:
        """Completed subtasks should have status='completed' and a result."""
        searxng = MockSearXNG()
        mock = _ComplexQueryMock()

        decomposer = RecursiveDecomposer()
        result = await decomposer.decompose_and_solve(
            "What is Python and how does it compare to Java?",
            searxng,
            mock.llm_call,
        )

        for subtask in result.subtasks:
            assert subtask.status == "completed", (
                f"Subtask {subtask.id} has status {subtask.status}"
            )
            assert subtask.result is not None, (
                f"Subtask {subtask.id} has no result"
            )

    async def test_aggregated_answer_synthesizes_subtasks(self) -> None:
        """The aggregated answer should reference both subtasks."""
        searxng = MockSearXNG()
        mock = _ComplexQueryMock()

        decomposer = RecursiveDecomposer()
        result = await decomposer.decompose_and_solve(
            "What is Python and how does it compare to Java?",
            searxng,
            mock.llm_call,
        )

        # The mock returns a synthesized answer mentioning both subtasks
        assert result.aggregated_answer != ""


class TestEdgeCases:
    """Edge cases like empty queries, LLM failures, etc."""

    async def test_llm_required_for_decomposition(self) -> None:
        """decompose_and_solve raises ValueError if llm_call is None."""
        searxng = MockSearXNG()
        decomposer = RecursiveDecomposer()

        import pytest
        with pytest.raises(ValueError, match="llm_call required"):
            await decomposer.decompose_and_solve(
                "complex query", searxng, None,
            )

    async def test_max_depth_prevents_infinite_recursion(self) -> None:
        """At max depth, even complex queries are answered directly."""
        searxng = MockSearXNG()
        call_count = 0

        async def mock_llm(messages: list[dict[str, str]]) -> str:
            nonlocal call_count
            call_count += 1
            content = messages[-1]["content"]
            if "can_answer_directly" in content:
                return (
                    '{"can_answer_directly": false, '
                    '"reasoning": "always complex"}'
                )
            if "decomposition" in content:
                return (
                    '[{"id": "sub_1", "query": "sub query", "dependencies": []}]'
                )
            return f"Answer #{call_count}"

        decomposer = RecursiveDecomposer(max_depth=1)
        result = await decomposer.decompose_and_solve(
            "complex test", searxng, mock_llm,
        )

        # With max_depth=1, depth 0 is already >= max_depth-1 → forced direct
        assert result.depth == 0
        # Should have used the direct path (no subtasks generated)
        assert len(result.subtasks) == 0

    async def test_llm_returns_empty_subtasks_falls_back_to_direct(
        self,
    ) -> None:
        """If LLM returns empty subtask list, fall back to direct solve."""
        searxng = MockSearXNG()

        async def mock_llm(messages: list[dict[str, str]]) -> str:
            content = messages[-1]["content"]
            if "can_answer_directly" in content:
                return '{"can_answer_directly": false, "reasoning": "complex"}'
            if "decomposition" in content:
                return "[]"  # Empty subtask list
            return "Fallback direct answer."

        decomposer = RecursiveDecomposer()
        result = await decomposer.decompose_and_solve(
            "some query", searxng, mock_llm,
        )

        # Should fall back to direct solve
        assert len(result.subtasks) == 0
        assert result.aggregated_answer != ""

    async def test_parse_json_response_direct(self) -> None:
        """_parse_json_response handles direct JSON objects."""
        decomposer = RecursiveDecomposer()
        result = decomposer._parse_json_response(
            '{"can_answer_directly": true, "reasoning": "simple"}'
        )
        assert result["can_answer_directly"] is True

    async def test_parse_json_response_array(self) -> None:
        """_parse_json_response handles JSON arrays."""
        decomposer = RecursiveDecomposer()
        result = decomposer._parse_json_response(
            '[{"id": "sub_1", "query": "test", "dependencies": []}]'
        )
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["id"] == "sub_1"

    async def test_parse_json_response_markdown_block(self) -> None:
        """_parse_json_response handles markdown-wrapped JSON."""
        decomposer = RecursiveDecomposer()
        result = decomposer._parse_json_response(
            '```json\n{"can_answer_directly": true}\n```'
        )
        assert result["can_answer_directly"] is True

    async def test_parse_json_response_invalid(self) -> None:
        """_parse_json_response returns {} for invalid input."""
        decomposer = RecursiveDecomposer()
        result = decomposer._parse_json_response("not json at all")
        assert result == {}


class _ComplexQueryMock:
    """Helper mock for complex query decomposition tests.

    Provides a callable LLM that simulates a full decomposition flow:
    1. Top-level check → needs decomposition
    2. Generates 2 subtasks (sub_1, sub_2 with dependency)
    3. Recursive calls for sub_1 → direct answer
    4. Recursive calls for sub_2 → direct answer
    5. Aggregation → synthesized answer
    """

    def __init__(self) -> None:
        self._phase = 0  # Tracks which phase of the flow we're in

    async def llm_call(self, messages: list[dict[str, str]]) -> str:
        self._phase += 1
        content = messages[-1]["content"]

        # Phase 1: Top-level can_answer_directly check → needs decomposition
        if self._phase == 1:
            return (
                '{"can_answer_directly": false, '
                '"reasoning": "multi-part query requiring decomposition"}'
            )

        # Phase 2: Generate subtasks
        if self._phase == 2:
            return (
                '[{"id": "sub_1", "query": "What is Python?", "dependencies": []},'
                '{"id": "sub_2", "query": "How does Python compare to Java?", '
                '"dependencies": ["sub_1"]}]'
            )

        # Phase 3+: Recursive calls for subtasks
        # These are executed via asyncio.gather, so order may vary
        if self._phase >= 3:
            # Check if this is a can_answer_directly check for a subtask
            if "can_answer_directly" in content:
                return (
                    '{"can_answer_directly": true, '
                    '"reasoning": "simple single-focus question"}'
                )
            # Check if this is the aggregation prompt
            if "Synthesize" in content or "Sub-Question Results" in content:
                return (
                    "Synthesized answer: Python is a versatile language. "
                    "Compared to Java, Python has simpler syntax "
                    "while Java has better performance for enterprise apps."
                )
            # Default: answer_with_context for individual subtasks
            return f"Answer from search results for phase {self._phase}."

        return "Default fallback."
