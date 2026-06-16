"""LLM-based tie-breaking verifier for multi-rollout answer voting.

When answer votes tie, this module uses an LLM call to evaluate the
competing answers on factual accuracy, source support, and completeness,
selecting the best one with a confidence rating.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import ClassVar

from browser_goat.models import ConfidenceLevel, ExtractedSource, VerificationResult

# ── Prompt Template ────────────────────────────────────────────────────────────


VERIFIER_PROMPT: str = """You are a precise answer verifier. Your task is to select the best answer from competing candidates by evaluating each against the original query and supporting sources.

## Query
{query}

## Candidates
{formatted_candidates}

## Sources
{formatted_sources}

## Evaluation Criteria

Score each candidate on three axes (1-10):

1. **Factual Accuracy** — Is the answer consistent with verifiable facts from the sources? Penalize hallucinations, contradictions, or information not supported by the sources.
2. **Source Support** — Does the answer cite or align with specific sources provided? Higher scores for answers that reflect the evidence accurately.
3. **Completeness** — Does the answer fully address the query? Penalize missing key aspects, partial answers, or irrelevant tangents.

## Output Format

Return valid JSON **only** — no markdown fences, no extra text:

```json
{{
  "selected_idx": 0,
  "confidence": "high",
  "reasoning": "Candidate A scores highest across all three axes...",
  "scores": [
    {{"factual_accuracy": 8, "source_support": 7, "completeness": 9}},
    {{"factual_accuracy": 6, "source_support": 5, "completeness": 7}}
  ]
}}
```

- `selected_idx`: 0-based index into the candidates list
- `confidence`: one of "high", "medium", "low"
- `reasoning`: 2-4 sentence explanation of your choice
- `scores`: one object per candidate, in the same order as the candidates list
"""


# ── LLM Verifier ────────────────────────────────────────────────────────────────


class LLMVerifier:
    """Breaks ties in multi-rollout voting by evaluating candidates via LLM.

    Uses targeted prompting to assess factual accuracy, source support,
    and completeness across competing answers.
    """

    _MAX_SOURCES_IN_PROMPT: ClassVar[int] = 10
    """Cap sources shown to the LLM to avoid token blowout."""

    async def verify(
        self,
        query: str,
        candidates: list[str],
        sources: list[ExtractedSource],
        llm_call: Callable[[str], Awaitable[str]] | None = None,
    ) -> VerificationResult:
        """Evaluate tied candidates via LLM and return the selected answer.

        Parameters
        ----------
        query:
            The original user query.
        candidates:
            Tied answer strings from the voting phase.
        sources:
            Extracted source objects used to form the answers.
        llm_call:
            Async callable that takes a prompt string and returns the LLM
            response. When ``None``, falls back to returning the first
            candidate with no confidence.

        Returns
        -------
        VerificationResult with selected answer, confidence, reasoning,
        and method indicator (``"llm"`` or ``"fallback"``).

        Edge cases
        ----------
        - Empty candidates → ``VerificationResult(method="fallback",
          confidence=NONE)`` with empty ``selected_answer``.
        - Single candidate → returned directly with ``MEDIUM`` confidence.
        - ``llm_call=None`` → fallback, first candidate returned with
          ``NONE`` confidence and ``method="fallback"``.
        - LLM returns unparseable output → fallback with ``LOW`` confidence.
        """
        # ── Edge cases that bypass LLM ──────────────────────────────────────
        if not candidates:
            return VerificationResult(
                selected_answer="",
                confidence=ConfidenceLevel.NONE,
                reasoning="No candidates provided to verifier.",
                method="fallback",
            )

        if len(candidates) == 1:
            return VerificationResult(
                selected_answer=candidates[0],
                confidence=ConfidenceLevel.MEDIUM,
                reasoning="Only one candidate; no tie to break.",
                method="fallback",
            )

        if llm_call is None:
            return VerificationResult(
                selected_answer=candidates[0],
                confidence=ConfidenceLevel.NONE,
                reasoning="No LLM callable provided; using fallback.",
                method="fallback",
            )

        # ── Build prompt ────────────────────────────────────────────────────
        formatted_candidates = "\n\n".join(
            f"Candidate {idx}:\n{answer}"
            for idx, answer in enumerate(candidates)
        )

        limited_sources = sources[: self._MAX_SOURCES_IN_PROMPT]
        source_lines: list[str] = []
        for idx, src in enumerate(limited_sources):
            summary = src.summary or "(no summary)"
            evidence = src.evidence or "(no evidence)"
            source_lines.append(
                f"Source {idx}: {src.title}\n"
                f"  URL: {src.url}\n"
                f"  Summary: {summary}\n"
                f"  Evidence: {evidence}\n"
            )
        formatted_sources = "\n".join(source_lines)

        prompt = VERIFIER_PROMPT.format(
            query=query,
            formatted_candidates=formatted_candidates,
            formatted_sources=formatted_sources,
        )

        # ── Call LLM ────────────────────────────────────────────────────────
        try:
            response = await llm_call(prompt)
        except Exception as exc:
            return VerificationResult(
                selected_answer=candidates[0],
                confidence=ConfidenceLevel.LOW,
                reasoning=f"LLM call failed: {exc}. Using fallback.",
                method="fallback",
            )

        # ── Parse LLM output ────────────────────────────────────────────────
        parsed = self._parse_response(response, len(candidates))
        if parsed is None:
            return VerificationResult(
                selected_answer=candidates[0],
                confidence=ConfidenceLevel.LOW,
                reasoning=f"Failed to parse LLM response: {response!r}. Using fallback.",
                method="fallback",
            )

        selected_idx, confidence_str, reasoning, _scores = parsed

        # Clamp index to valid range
        if selected_idx < 0 or selected_idx >= len(candidates):
            selected_idx = 0
            confidence_str = "low"
            reasoning = (
                f"LLM returned invalid index {selected_idx}; using fallback."
            )

        confidence = self._parse_confidence(confidence_str)

        return VerificationResult(
            selected_answer=candidates[selected_idx],
            confidence=confidence,
            reasoning=reasoning,
            method="llm",
        )

    # ── Internal helpers ────────────────────────────────────────────────────

    @staticmethod
    def _parse_response(
        response: str,
        num_candidates: int,
    ) -> tuple[int, str, str, list[dict[str, int]]] | None:
        """Extract ``(selected_idx, confidence, reasoning, scores)`` from LLM JSON.

        Tolerates markdown fences, leading/trailing text, and minor JSON
        quirks. Returns ``None`` when parsing fails entirely.
        """
        # Strip markdown code fences if present
        text = response.strip()
        if text.startswith("```"):
            # Remove opening fence (possibly with language hint)
            first_newline = text.find("\n")
            if first_newline != -1:
                text = text[first_newline:]
            # Remove closing fence
            closing = text.rfind("```")
            if closing != -1:
                text = text[:closing]
            text = text.strip()

        # Locate JSON object
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None

        raw = text[start : end + 1]
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None

        selected_idx = data.get("selected_idx", 0)
        confidence = data.get("confidence", "low")
        reasoning = data.get("reasoning", "")
        scores = data.get("scores", [])

        if not isinstance(selected_idx, int):
            selected_idx = 0
        if not isinstance(confidence, str):
            confidence = "low"
        if not isinstance(reasoning, str):
            reasoning = str(reasoning)
        if not isinstance(scores, list):
            scores = []

        return (selected_idx, confidence, reasoning, scores)

    @staticmethod
    def _parse_confidence(value: str) -> ConfidenceLevel:
        """Map LLM confidence string to ``ConfidenceLevel`` enum."""
        lower = value.strip().lower()
        if lower == "high":
            return ConfidenceLevel.HIGH
        if lower == "medium":
            return ConfidenceLevel.MEDIUM
        if lower == "low":
            return ConfidenceLevel.LOW
        return ConfidenceLevel.NONE
