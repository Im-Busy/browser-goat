"""Tests for Quality Gate."""

from __future__ import annotations

from browser_goat.models import ExtractedSource
from browser_goat.reliability.quality_gate import QualityGate


def _make_source(url: str = "https://example.com", summary: str = "Test summary") -> ExtractedSource:
    """Helper to create an ExtractedSource for testing."""
    return ExtractedSource(
        url=url,
        title="Test Title",
        rational="Relevant because test",
        evidence="Test evidence content here.",
        summary=summary,
        extraction_tier=3,
        used_scrapling=False,
        rank=1,
        final_score=1.0,
        engine="google",
    )


class TestCheck:
    def test_answer_too_short_fails(self) -> None:
        gate = QualityGate()
        result = gate.check("Too short", sources=[])
        assert result.passed is False
        assert result.reason is not None
        assert "answer_too_short" in result.reason

    def test_no_citations_fails_when_sources_exist(self) -> None:
        gate = QualityGate()
        answer = (
            "Python is a high-level programming language created by Guido van Rossum. "
            "It emphasizes code readability with significant indentation. "
            "This answer is long enough but lacks any citation markers."
        )
        sources = [_make_source(url="https://python.org")]
        result = gate.check(answer, sources=sources)
        assert result.passed is False
        assert result.reason == "no_citations"

    def test_valid_answer_with_citations_passes(self) -> None:
        gate = QualityGate()
        answer = (
            "Python is a high-level programming language [1]. "
            "It was created by Guido van Rossum and first released in 1991 [2]. "
            "Python is widely used in data science, web development, and automation [1]."
        )
        sources = [
            _make_source(url="https://python.org", summary="Python language overview"),
            _make_source(url="https://wikipedia.org/python", summary="Python history"),
        ]
        result = gate.check(answer, sources=sources)
        assert result.passed is True
        assert result.reason is None

    def test_valid_answer_no_sources_no_citations_passes(self) -> None:
        """If no sources are provided, missing citations is not a failure."""
        gate = QualityGate()
        answer = (
            "This is a sufficiently long answer that doesn't need citations "
            "because there are no sources to cite from. The length alone is adequate."
        )
        result = gate.check(answer, sources=[])
        assert result.passed is True
        assert result.reason is None

    def test_tracks_retries_used(self) -> None:
        gate = QualityGate()
        result = gate.check("Too short", sources=[], retries_used=2)
        assert result.passed is False
        assert result.retries_used == 2

    def test_custom_min_length(self) -> None:
        gate = QualityGate(min_length=200)
        answer = (
            "This answer is 80+ chars long enough for the default min, "
            "but should fail with min_length=200."
        )
        result = gate.check(answer, sources=[])
        assert result.passed is False
        assert "answer_too_short" in (result.reason or "")

    def test_edge_case_exactly_min_length_passes(self) -> None:
        gate = QualityGate(min_length=80)
        exact = "A" * 80
        result = gate.check(exact, sources=[])
        assert result.passed is True
