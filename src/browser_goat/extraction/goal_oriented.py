"""Goal-Oriented Extraction — rational/evidence/summary per page.

Ported from Tongyi-DeepResearch inference/tool_visit.py.
Uses an LLM to produce structured extraction:
  - rational: Why this page is relevant to the query
  - evidence: Specific text passages that answer the query
  - summary: Condensed 2-3 sentence summary
"""

from __future__ import annotations

import json
import re
import typing
from typing import Any

import tiktoken

from browser_goat.models import ExtractedContent, GoalOrientedResult

# ── Extraction Prompt (from Tongyi prompt.py) ────────────────────────────────

EXTRACTOR_PROMPT = """You are a research assistant extracting information from a webpage.

## TASK
Extract structured information from the page content below.

## USER GOAL
{goal}

## PAGE INFORMATION
Title: {title}
URL: {url}

## CONTENT
{content}

## OUTPUT FORMAT
Return ONLY a JSON object with these three fields:
1. "rational": Which sections or data on this page are relevant to the user's goal? Be concise (1-2 sentences).
2. "evidence": What specific information from the page helps achieve the goal? Include key facts, data points, and direct quotes. Preserve the original context — do not paraphrase away details. This should be multiple sentences if needed.
3. "summary": A concise 2-3 sentence summary of what this page contributes to the goal. Include the most important finding.

IMPORTANT:
- Only use information actually present in the page content.
- If the page does not contain relevant information, state that clearly.
- Return ONLY valid JSON. No other text.
"""

# ── Token Limit ──────────────────────────────────────────────────────────────

MAX_TOKENS = 95000
FALLBACK_TOKENS = 25000


class GoalOrientedExtractor:
    """Extract goal-oriented rational/evidence/summary from page content.

    Requires an async LLM callable with signature:
        async def llm_call(messages: list[dict]) -> str
    """

    def __init__(
        self,
        llm_call: Any = None,
        max_tokens: int = MAX_TOKENS,
        fallback_tokens: int = FALLBACK_TOKENS,
    ) -> None:
        self._llm_call = llm_call
        self.max_tokens = max_tokens
        self.fallback_tokens = fallback_tokens
        self._tokenizer = tiktoken.get_encoding("cl100k_base")

    async def extract(
        self,
        content: ExtractedContent,
        query: str,
    ) -> GoalOrientedResult:
        """Extract goal-oriented summary from page content.

        Args:
            content: Extracted page content.
            query: The original search query (used as the "goal").

        Returns:
            GoalOrientedResult with rational, evidence, and summary populated.
        """
        base = GoalOrientedResult(
            url=content.url,
            title=content.title,
            text=content.text,
            extraction_tier=content.extraction_tier,
            word_count=content.word_count,
        )

        if not content.text or not self._llm_call:
            # No LLM available — use the extracted text as evidence
            base.rational = f"This page may be relevant to: {query}"
            base.evidence = content.text[:2000]
            base.summary = content.text[:500]
            return base

        # Truncate to token budget
        truncated = self._truncate_to_tokens(content.text, self.max_tokens)

        prompt = EXTRACTOR_PROMPT.format(
            goal=query,
            title=content.title,
            url=content.url,
            content=truncated,
        )

        try:
            messages = [{"role": "user", "content": prompt}]
            raw_response = await self._llm_call(messages)

            # Parse JSON from response
            parsed = self._parse_json(raw_response)

            base.rational = parsed.get("rational", "")
            base.evidence = parsed.get("evidence", "")
            base.summary = parsed.get("summary", "")

            # If response is too short, retry with truncated content
            if len(raw_response) < 50:
                truncated = self._truncate_to_tokens(content.text, self.fallback_tokens)
                prompt = EXTRACTOR_PROMPT.format(
                    goal=query,
                    title=content.title,
                    url=content.url,
                    content=truncated,
                )
                messages = [{"role": "user", "content": prompt}]
                raw_response = await self._llm_call(messages)
                parsed = self._parse_json(raw_response)
                base.rational = parsed.get("rational", "")
                base.evidence = parsed.get("evidence", "")
                base.summary = parsed.get("summary", "")

        except Exception:
            # On failure, use raw text as fallback
            base.rational = f"Relevant to query: {query}"
            base.evidence = content.text[:2000]
            base.summary = content.text[:500]

        return base

    def _truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        """Truncate text to fit within token budget."""
        tokens = self._tokenizer.encode(text)
        if len(tokens) <= max_tokens:
            return text

        truncated_tokens = tokens[:max_tokens]
        return self._tokenizer.decode(truncated_tokens)

    def _parse_json(self, text: str) -> dict[str, str]:
        """Parse JSON from LLM response, handling markdown code blocks."""
        # Try direct JSON parse
        try:
            return typing.cast("dict[str, str]", json.loads(text))
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code blocks
        for pattern in [r"```json\s*(\{.*?\})\s*```", r"```\s*(\{.*?\})\s*```", r"\{.*?\}"]:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    return typing.cast("dict[str, str]", json.loads(match.group(1)))
                except (json.JSONDecodeError, IndexError):
                    continue

        # Fallback: return empty dict
        return {}
