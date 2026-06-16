"""Tests for LLM verifier."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from browser_goat.models import ConfidenceLevel, ExtractedSource
from browser_goat.verification.llm_verifier import LLMVerifier


def _make_source(url: str = "https://example.com") -> ExtractedSource:
    return ExtractedSource(
        url=url,
        title="Example Source",
        rational="Relevant page.",
        evidence="Key evidence here.",
        summary="A short summary.",
        extraction_tier=3,
        used_scrapling=False,
        rank=1,
        final_score=0.85,
        engine="google",
    )


class TestVerify:
    @pytest.mark.asyncio
    async def test_llm_breaks_tie(self) -> None:
        """When candidates are tied, the LLM is called and the selected answer returned."""
        llm_call = AsyncMock(return_value=(
            '{"selected_idx": 1, "confidence": "high", "reasoning": "Candidate B is more accurate.", "scores": []}'
        ))
        verifier = LLMVerifier()
        sources = [_make_source(), _make_source()]
        result = await verifier.verify(
            query="What is the best language?",
            candidates=["Candidate A", "Candidate B"],
            sources=sources,
            llm_call=llm_call,
        )
        assert result.selected_answer == "Candidate B"
        assert result.confidence == ConfidenceLevel.HIGH
        assert result.method == "llm"
        llm_call.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_single_candidate_returns_directly(self) -> None:
        """Single candidate bypasses LLM entirely."""
        verifier = LLMVerifier()
        sources = [_make_source()]
        result = await verifier.verify(
            query="test",
            candidates=["The only answer."],
            sources=sources,
            llm_call=None,
        )
        assert result.selected_answer == "The only answer."
        assert result.confidence == ConfidenceLevel.MEDIUM
        assert result.method == "fallback"

    @pytest.mark.asyncio
    async def test_empty_candidates_handles_gracefully(self) -> None:
        """Empty candidate list returns empty result with NONE confidence."""
        verifier = LLMVerifier()
        result = await verifier.verify(
            query="test",
            candidates=[],
            sources=[],
            llm_call=AsyncMock(),
        )
        assert result.selected_answer == ""
        assert result.confidence == ConfidenceLevel.NONE
        assert result.method == "fallback"
        assert "No candidates" in result.reasoning

    @pytest.mark.asyncio
    async def test_no_llm_callable_falls_back(self) -> None:
        """When llm_call is None, falls back to first candidate with NONE confidence."""
        verifier = LLMVerifier()
        sources = [_make_source(), _make_source()]
        result = await verifier.verify(
            query="test",
            candidates=["First answer.", "Second answer."],
            sources=sources,
            llm_call=None,
        )
        assert result.selected_answer == "First answer."
        assert result.confidence == ConfidenceLevel.NONE
        assert result.method == "fallback"

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back(self) -> None:
        """When LLM raises an exception, falls back with LOW confidence."""
        llm_call = AsyncMock(side_effect=RuntimeError("API timeout"))
        verifier = LLMVerifier()
        sources = [_make_source(), _make_source()]
        result = await verifier.verify(
            query="test",
            candidates=["First answer.", "Second answer."],
            sources=sources,
            llm_call=llm_call,
        )
        assert result.selected_answer == "First answer."
        assert result.confidence == ConfidenceLevel.LOW
        assert result.method == "fallback"

    @pytest.mark.asyncio
    async def test_unparseable_llm_response_falls_back(self) -> None:
        """When LLM returns invalid JSON, falls back with LOW confidence."""
        llm_call = AsyncMock(return_value="This is not JSON at all")
        verifier = LLMVerifier()
        sources = [_make_source(), _make_source()]
        result = await verifier.verify(
            query="test",
            candidates=["First answer.", "Second answer."],
            sources=sources,
            llm_call=llm_call,
        )
        assert result.selected_answer == "First answer."
        assert result.confidence == ConfidenceLevel.LOW
        assert result.method == "fallback"

    @pytest.mark.asyncio
    async def test_invalid_index_clamped_to_zero(self) -> None:
        """When LLM returns an out-of-range index, it is clamped to 0."""
        llm_call = AsyncMock(return_value=(
            '{"selected_idx": 99, "confidence": "high", "reasoning": "Candidate A is best.", "scores": []}'
        ))
        verifier = LLMVerifier()
        sources = [_make_source(), _make_source()]
        result = await verifier.verify(
            query="test",
            candidates=["First answer.", "Second answer."],
            sources=sources,
            llm_call=llm_call,
        )
        assert result.selected_answer == "First answer."
        assert result.confidence == ConfidenceLevel.LOW

    @pytest.mark.asyncio
    async def test_sources_truncated_to_max(self) -> None:
        """When there are more sources than MAX_SOURCES_IN_PROMPT, they are truncated."""
        llm_call = AsyncMock(return_value=(
            '{"selected_idx": 0, "confidence": "medium", "reasoning": "Candidate A is accurate.", "scores": []}'
        ))
        verifier = LLMVerifier()
        many_sources = [_make_source(url=f"https://example.com/{i}") for i in range(20)]
        result = await verifier.verify(
            query="test",
            candidates=["Candidate A", "Candidate B"],
            sources=many_sources,
            llm_call=llm_call,
        )
        assert result.selected_answer == "Candidate A"
        assert result.confidence == ConfidenceLevel.MEDIUM
        assert result.method == "llm"

    @pytest.mark.asyncio
    async def test_llm_response_with_markdown_fences(self) -> None:
        """LLM responses wrapped in markdown code fences are parsed correctly."""
        llm_call = AsyncMock(return_value=(
            "```json\n"
            '{"selected_idx": 0, "confidence": "high", "reasoning": "A is correct.", "scores": []}\n'
            "```"
        ))
        verifier = LLMVerifier()
        sources = [_make_source(), _make_source()]
        result = await verifier.verify(
            query="test",
            candidates=["A", "B"],
            sources=sources,
            llm_call=llm_call,
        )
        assert result.selected_answer == "A"
        assert result.confidence == ConfidenceLevel.HIGH
        assert result.reasoning == "A is correct."


class TestParseResponse:
    def test_valid_json_parsed(self) -> None:
        result = LLMVerifier._parse_response(
            '{"selected_idx": 0, "confidence": "high", "reasoning": "Best.", "scores": []}',
            num_candidates=2,
        )
        assert result is not None
        idx, confidence, reasoning, scores = result
        assert idx == 0
        assert confidence == "high"
        assert reasoning == "Best."

    def test_markdown_fences_stripped(self) -> None:
        result = LLMVerifier._parse_response(
            "```\n{\"selected_idx\": 1, \"confidence\": \"low\", \"reasoning\": \"Nope.\", \"scores\": []}\n```",
            num_candidates=2,
        )
        assert result is not None
        assert result[0] == 1
        assert result[1] == "low"

    def test_invalid_json_returns_none(self) -> None:
        result = LLMVerifier._parse_response("not json at all", num_candidates=2)
        assert result is None

    def test_empty_response_returns_none(self) -> None:
        result = LLMVerifier._parse_response("", num_candidates=2)
        assert result is None

    def test_missing_fields_default_to_zero(self) -> None:
        result = LLMVerifier._parse_response(
            '{"selected_idx": 2, "scores": []}',
            num_candidates=5,
        )
        assert result is not None
        assert result[0] == 2
        assert result[1] == "low"  # default
        assert result[2] == ""  # default


class TestParseConfidence:
    def test_high(self) -> None:
        assert LLMVerifier._parse_confidence("high") == ConfidenceLevel.HIGH

    def test_medium(self) -> None:
        assert LLMVerifier._parse_confidence("medium") == ConfidenceLevel.MEDIUM

    def test_low(self) -> None:
        assert LLMVerifier._parse_confidence("low") == ConfidenceLevel.LOW

    def test_unknown_defaults_to_none(self) -> None:
        assert LLMVerifier._parse_confidence("unknown") == ConfidenceLevel.NONE

    def test_case_insensitive(self) -> None:
        assert LLMVerifier._parse_confidence("HIGH") == ConfidenceLevel.HIGH
        assert LLMVerifier._parse_confidence("Medium") == ConfidenceLevel.MEDIUM
