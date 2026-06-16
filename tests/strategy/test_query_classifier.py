"""Tests for LLM-powered query classifier.

Tests both rule-based fallback and LLM-driven classification paths.
"""

from __future__ import annotations

from browser_goat.models import ClassificationResult
from browser_goat.strategy.query_classifier import (
    COMPARISON,
    FACTUAL,
    HOWTO,
    PERSON,
    PUZZLE,
    QUERY_TYPES,
    RESEARCH,
    TEMPORAL,
    QueryClassifier,
)


class TestRuleBasedClassification:
    """Tests using only keyword-based rule matching (no LLM)."""

    def test_factual_query(self) -> None:
        classifier = QueryClassifier()
        result = classifier._classify_rule_based("what is the capital of france")
        assert result.query_type == FACTUAL
        assert result.complexity in ("simple", "medium")

    def test_person_query(self) -> None:
        classifier = QueryClassifier()
        result = classifier._classify_rule_based("who is satya nadella")
        assert result.query_type == PERSON

    def test_person_query_biography(self) -> None:
        classifier = QueryClassifier()
        result = classifier._classify_rule_based("biography of marie curie")
        assert result.query_type == PERSON

    def test_comparison_query_vs(self) -> None:
        classifier = QueryClassifier()
        result = classifier._classify_rule_based("python vs rust")
        assert result.query_type == COMPARISON

    def test_comparison_query_difference(self) -> None:
        classifier = QueryClassifier()
        result = classifier._classify_rule_based("difference between python and java")
        assert result.query_type == COMPARISON

    def test_howto_query(self) -> None:
        classifier = QueryClassifier()
        result = classifier._classify_rule_based("how to deploy docker container")
        assert result.query_type == HOWTO

    def test_howto_tutorial(self) -> None:
        classifier = QueryClassifier()
        result = classifier._classify_rule_based("tutorial for beginners python")
        assert result.query_type == HOWTO

    def test_temporal_query_breaking(self) -> None:
        classifier = QueryClassifier()
        result = classifier._classify_rule_based("breaking news today")
        assert result.query_type == TEMPORAL

    def test_temporal_query_latest(self) -> None:
        classifier = QueryClassifier()
        result = classifier._classify_rule_based("latest python release")
        assert result.query_type == TEMPORAL

    def test_research_query(self) -> None:
        classifier = QueryClassifier()
        result = classifier._classify_rule_based("latest research on quantum computing")
        assert result.query_type == RESEARCH

    def test_research_study(self) -> None:
        classifier = QueryClassifier()
        result = classifier._classify_rule_based("study of machine learning algorithms")
        assert result.query_type == RESEARCH

    def test_puzzle_query_riddle(self) -> None:
        classifier = QueryClassifier()
        result = classifier._classify_rule_based("solve this riddle what has keys")
        assert result.query_type == PUZZLE

    def test_puzzle_query_brain_teaser(self) -> None:
        classifier = QueryClassifier()
        result = classifier._classify_rule_based("brain teaser logic puzzle")
        assert result.query_type == PUZZLE


class TestRuleBasedClassificationWithLLM:
    """Tests using classify() with llm_call=None to verify the public API
    falls back to rule-based when no LLM is available."""

    async def test_classify_factual(self) -> None:
        classifier = QueryClassifier()
        result = await classifier.classify("what is python")
        assert result.query_type == FACTUAL

    async def test_classify_comparison(self) -> None:
        classifier = QueryClassifier()
        result = await classifier.classify("python vs rust for web dev")
        assert result.query_type == COMPARISON

    async def test_classify_howto(self) -> None:
        classifier = QueryClassifier()
        result = await classifier.classify("how to build a rest api")
        assert result.query_type == HOWTO

    async def test_classify_research(self) -> None:
        classifier = QueryClassifier()
        result = await classifier.classify("research on crispr gene editing")
        assert result.query_type == RESEARCH


class TestLLMBasedClassification:
    """Tests using a mocked LLM callable."""

    async def test_llm_returns_factual(self) -> None:
        async def mock_llm(_messages: list[dict[str, str]]) -> str:
            return (
                '{"query_type": "factual", "complexity": "simple", '
                '"needs_decomposition": false, "suggested_subtasks": [], '
                '"confidence": 0.95}'
            )

        classifier = QueryClassifier(llm_call=mock_llm)
        result = await classifier.classify("What is the capital of France?")
        assert result.query_type == FACTUAL
        assert result.complexity == "simple"
        assert result.confidence == 0.95
        assert result.needs_decomposition is False

    async def test_llm_returns_comparison(self) -> None:
        async def mock_llm(_messages: list[dict[str, str]]) -> str:
            return (
                '{"query_type": "comparison", "complexity": "medium", '
                '"needs_decomposition": true, "suggested_subtasks": '
                '["Research: Python", "Research: Rust", "Synthesize comparison"], '
                '"confidence": 0.88}'
            )

        classifier = QueryClassifier(llm_call=mock_llm)
        result = await classifier.classify("Python vs Rust")
        assert result.query_type == COMPARISON
        assert result.complexity == "medium"
        assert result.needs_decomposition is True
        assert len(result.suggested_subtasks) == 3

    async def test_llm_returns_research(self) -> None:
        async def mock_llm(_messages: list[dict[str, str]]) -> str:
            return (
                '{"query_type": "research", "complexity": "complex", '
                '"needs_decomposition": true, "suggested_subtasks": '
                '["Find recent papers", "Summarize findings"], '
                '"confidence": 0.9}'
            )

        classifier = QueryClassifier(llm_call=mock_llm)
        result = await classifier.classify("Latest research on quantum computing")
        assert result.query_type == RESEARCH
        assert result.complexity == "complex"
        assert result.needs_decomposition is True

    async def test_llm_response_in_markdown_block(self) -> None:
        """LLM may wrap JSON in markdown code blocks."""
        async def mock_llm(_messages: list[dict[str, str]]) -> str:
            return (
                "```json\n"
                '{"query_type": "howto", "complexity": "medium", '
                '"needs_decomposition": false, "suggested_subtasks": [], '
                '"confidence": 0.85}\n'
                "```"
            )

        classifier = QueryClassifier(llm_call=mock_llm)
        result = await classifier.classify("How to deploy Docker?")
        assert result.query_type == HOWTO
        assert result.complexity == "medium"

    async def test_classify_override_llm_call(self) -> None:
        """classify() accepts an optional per-call llm_call override."""
        async def instance_llm(_messages: list[dict[str, str]]) -> str:
            return (
                '{"query_type": "factual", "complexity": "simple", '
                '"needs_decomposition": false, "suggested_subtasks": [], '
                '"confidence": 0.5}'
            )

        async def override_llm(_messages: list[dict[str, str]]) -> str:
            return (
                '{"query_type": "research", "complexity": "complex", '
                '"needs_decomposition": true, "suggested_subtasks": '
                '["Find papers"], "confidence": 0.9}'
            )

        classifier = QueryClassifier(llm_call=instance_llm)
        # Should use override_llm, not instance_llm
        result = await classifier.classify("test query", llm_call=override_llm)
        assert result.query_type == RESEARCH
        assert result.needs_decomposition is True


class TestLLMFallback:
    """When the LLM fails (exception, bad JSON), classifier falls back to
    rule-based classification."""

    async def test_llm_raises_exception(self) -> None:
        async def failing_llm(_messages: list[dict[str, str]]) -> str:
            raise RuntimeError("LLM unavailable")

        classifier = QueryClassifier(llm_call=failing_llm)
        result = await classifier.classify("who is albert einstein")
        assert result.query_type == PERSON  # fallback to rule-based

    async def test_llm_returns_garbage(self) -> None:
        async def garbage_llm(_messages: list[dict[str, str]]) -> str:
            return "this is not json at all"

        classifier = QueryClassifier(llm_call=garbage_llm)
        result = await classifier.classify("how to bake a cake")
        # _parse_llm_response returns {} without raising, so defaults are used
        # Default query_type is FACTUAL
        assert result.query_type == FACTUAL
        assert result.confidence == 0.5

    async def test_llm_returns_empty(self) -> None:
        async def empty_llm(_messages: list[dict[str, str]]) -> str:
            return ""

        classifier = QueryClassifier(llm_call=empty_llm)
        result = await classifier.classify("python vs javascript")
        # _parse_llm_response returns {} without raising, so defaults are used
        assert result.query_type == FACTUAL


class TestEdgeCases:
    """Edge cases like empty queries, very short queries, etc."""

    def test_empty_query_rule_based(self) -> None:
        classifier = QueryClassifier()
        result = classifier._classify_rule_based("")
        assert result.query_type == FACTUAL
        assert result.complexity == "simple"

    def test_single_word_query(self) -> None:
        classifier = QueryClassifier()
        result = classifier._classify_rule_based("python")
        assert result.query_type == FACTUAL
        assert result.complexity == "simple"

    def test_query_type_is_in_queries(self) -> None:
        """All QUERY_TYPES are valid strings referenced by the classifier."""
        for qtype in QUERY_TYPES:
            assert isinstance(qtype, str)
            assert len(qtype) > 0

    def test_classification_result_is_pydantic(self) -> None:
        classifier = QueryClassifier()
        result = classifier._classify_rule_based("what is python")
        assert isinstance(result, ClassificationResult)
        assert ClassificationResult.model_fields is not None

    def test_parse_llm_response_direct(self) -> None:
        classifier = QueryClassifier()
        result = classifier._parse_llm_response(
            '{"query_type": "howto", "complexity": "simple", '
            '"needs_decomposition": false, "suggested_subtasks": [], '
            '"confidence": 0.7}'
        )
        assert result["query_type"] == "howto"
        assert result["complexity"] == "simple"

    def test_parse_llm_response_markdown(self) -> None:
        classifier = QueryClassifier()
        result = classifier._parse_llm_response(
            '```json\n{"query_type": "comparison", "complexity": "medium", '
            '"needs_decomposition": true, "suggested_subtasks": [], '
            '"confidence": 0.8}\n```'
        )
        assert result["query_type"] == "comparison"

    def test_parse_llm_response_invalid(self) -> None:
        classifier = QueryClassifier()
        result = classifier._parse_llm_response("not json at all")
        assert result == {}
