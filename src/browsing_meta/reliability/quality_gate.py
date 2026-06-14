"""Quality Gate — retry on insufficient LLM answers.

Ported from SearchWala llm.rs: answer_quality_insufficient().
Checks if answer is too short or missing citations.
"""

from __future__ import annotations

import re

from browsing_meta.models import ExtractedSource, QualityResult


class QualityGate:
    """Check LLM answer quality and retry if insufficient.

    Two checks:
    1. Answer length < 80 chars → likely too short to be useful
    2. Answer has no citation markers [1], [2], etc. → unsubstantiated
    """

    MIN_ANSWER_LENGTH: int = 80
    MAX_RETRIES: int = 1

    # Pattern to detect citation markers like [1], [2], [source], [ref]
    CITATION_PATTERN: re.Pattern[str] = re.compile(r"\[\d+\]")

    def __init__(self, min_length: int = 80, max_retries: int = 1) -> None:
        self.min_length = min_length or self.MIN_ANSWER_LENGTH
        self.max_retries = max_retries

    def check(
        self,
        answer: str,
        sources: list[ExtractedSource],
        retries_used: int = 0,
    ) -> QualityResult:
        """Check if answer meets quality thresholds.

        Args:
            answer: The synthesized answer text.
            sources: The sources used to generate the answer.
            retries_used: How many retries have already been attempted.

        Returns:
            QualityResult with pass/fail and reason.
        """
        # Check 1: Answer too short
        if len(answer.strip()) < self.min_length:
            return QualityResult(
                passed=False,
                reason=f"answer_too_short ({len(answer)} chars < {self.min_length})",
                retries_used=retries_used,
            )

        # Check 2: No citations in answer when sources exist
        if sources and not self.CITATION_PATTERN.search(answer):
            return QualityResult(
                passed=False,
                reason="no_citations",
                retries_used=retries_used,
            )

        return QualityResult(passed=True, retries_used=retries_used)
