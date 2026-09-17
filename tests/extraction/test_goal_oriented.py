"""Tests for Goal-Oriented Extractor."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from browser_goat.extraction.goal_oriented import GoalOrientedExtractor
from browser_goat.models import ExtractedContent


class TestGoalOrientedExtractor:
    def test_no_llm_fallback(self) -> None:
        extractor = GoalOrientedExtractor(llm_call=None)
        content = ExtractedContent(
            url="https://example.com",
            title="Test",
            text="Sample page content.",
            extraction_tier=3,
        )
        result = asyncio.run(extractor.extract(content, "test query"))

        assert result.rational != ""
        assert result.evidence != ""
        assert result.summary != ""

    def test_truncate_to_tokens(self) -> None:
        extractor = GoalOrientedExtractor()
        long_text = "hello world " * 50000
        # Exercise truncation without downloading a vendor-hosted tokenizer file.
        encoding = MagicMock()
        encoding.encode.side_effect = lambda text: list(text)
        encoding.decode.side_effect = lambda tokens: "".join(tokens)
        with patch("tiktoken.get_encoding", return_value=encoding):
            truncated = extractor._truncate_to_tokens(long_text, 100)
        assert len(truncated) == 100

    def test_parse_json_direct(self) -> None:
        extractor = GoalOrientedExtractor()
        result = extractor._parse_json('{"rational": "test", "evidence": "evidence", "summary": "summary"}')
        assert result["rational"] == "test"
        assert result["evidence"] == "evidence"

    def test_parse_json_markdown_block(self) -> None:
        extractor = GoalOrientedExtractor()
        result = extractor._parse_json(
            '```json\n{"rational": "test", "evidence": "ev", "summary": "sum"}\n```'
        )
        assert result["rational"] == "test"

    def test_parse_json_invalid(self) -> None:
        extractor = GoalOrientedExtractor()
        result = extractor._parse_json("not json at all")
        assert result == {}
