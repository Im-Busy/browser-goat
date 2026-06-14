"""Tests for Force Answer synthesis."""

from __future__ import annotations

from browsing_meta.models import ExtractedSource
from browsing_meta.reliability.force_answer import (
    FORCE_ANSWER_PROMPT,
    build_force_answer_prompt,
    format_sources_for_prompt,
)


def _make_source(
    url: str = "https://example.com",
    evidence: str = "Example evidence content.",
    summary: str = "",
) -> ExtractedSource:
    """Helper to create an ExtractedSource for testing."""
    return ExtractedSource(
        url=url,
        title="Test Title",
        rational="Relevant because test",
        evidence=evidence,
        summary=summary,
        extraction_tier=3,
        used_scrapling=False,
        rank=1,
        final_score=1.0,
        engine="google",
    )


class TestBuildForceAnswerPrompt:
    def test_includes_query(self) -> None:
        prompt = build_force_answer_prompt(
            query="What is Python?",
            sources_text="[1] https://python.org\nPython is a language.",
        )
        assert "What is Python?" in prompt

    def test_includes_sources(self) -> None:
        prompt = build_force_answer_prompt(
            query="What is Python?",
            sources_text="[1] https://python.org\nPython is a language.",
        )
        assert "[1] https://python.org" in prompt
        assert "Python is a language." in prompt

    def test_prompt_has_expected_sections(self) -> None:
        prompt = build_force_answer_prompt(
            query="test",
            sources_text="test sources",
        )
        assert "## RULES" in prompt
        assert "## SOURCES" in prompt
        assert "## QUERY" in prompt
        assert "## YOUR ANSWER" in prompt

    def test_prompt_mentions_inline_citations(self) -> None:
        prompt = build_force_answer_prompt(query="test", sources_text="test")
        assert "[1]" in prompt or "citations" in prompt
        assert "confidence" in prompt.lower()

    def test_empty_sources_text(self) -> None:
        prompt = build_force_answer_prompt(query="test", sources_text="")
        assert prompt.count("test") >= 1


class TestFormatSourcesForPrompt:
    def test_formats_single_source(self) -> None:
        source = _make_source(url="https://python.org", evidence="Python is a programming language.")
        result = format_sources_for_prompt([source])
        assert "[1]" in result
        assert "https://python.org" in result
        assert "Python is a programming language." in result

    def test_formats_multiple_sources_with_numbering(self) -> None:
        sources = [
            _make_source(url="https://python.org", evidence="Python info."),
            _make_source(url="https://docs.python.org", evidence="Python docs."),
        ]
        result = format_sources_for_prompt(sources)
        assert "[1]" in result
        assert "[2]" in result
        assert "https://python.org" in result
        assert "https://docs.python.org" in result

    def test_handles_empty_sources(self) -> None:
        result = format_sources_for_prompt([])
        assert result == "No sources available."

    def test_truncates_long_sources(self) -> None:
        source = _make_source(
            url="https://python.org",
            evidence="A" * 2000,
        )
        result = format_sources_for_prompt([source], max_source_chars=100)
        # evidence per source is capped at 500 chars, but when total exceeds
        # max_source_chars on first entry, no more entries are added
        assert len(result) > 100
        assert "[1]" in result
        assert "more sources omitted" not in result

    def test_uses_summary_fallback(self) -> None:
        source = ExtractedSource(
            url="https://python.org",
            title="Python",
            rational="test",
            evidence="",  # empty evidence
            summary="Summary fallback content here.",
            extraction_tier=3,
            used_scrapling=False,
            rank=1,
            final_score=1.0,
            engine="google",
        )
        result = format_sources_for_prompt([source])
        assert "Summary fallback content here." in result

    def test_separates_sources_with_newlines(self) -> None:
        sources = [
            _make_source(url="https://a.com", evidence="Source A."),
            _make_source(url="https://b.com", evidence="Source B."),
        ]
        result = format_sources_for_prompt(sources)
        assert "\n\n" in result

    def test_omitted_sources_note_when_overflow(self) -> None:
        sources = [
            _make_source(url=f"https://example{i}.com", evidence="X" * 300)
            for i in range(10)
        ]
        result = format_sources_for_prompt(sources, max_source_chars=200)
        assert "more sources omitted" in result


class TestForceAnswerPromptConstant:
    def test_has_query_placeholder(self) -> None:
        assert "{query}" in FORCE_ANSWER_PROMPT

    def test_has_sources_placeholder(self) -> None:
        assert "{sources}" in FORCE_ANSWER_PROMPT

    def test_has_rules_section(self) -> None:
        assert "RULES" in FORCE_ANSWER_PROMPT
        assert "YOUR ANSWER" in FORCE_ANSWER_PROMPT
