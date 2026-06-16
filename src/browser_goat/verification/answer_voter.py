"""Pure-logic answer voting for multi-rollout verification.

Groups similar answers by normalized text, counts votes,
and returns a VoteResult with confidence level and consensus status.
"""

from __future__ import annotations

import difflib
import re
from typing import ClassVar

from browser_goat.models import ConfidenceLevel, VoteResult

_SIMILARITY_THRESHOLD: float = 0.85
_CONSENSUS_WINNER_MIN_VOTES: int = 4


class AnswerVoter:
    """Groups similar answers by normalized text and returns voting results.

    Pure synchronous logic — no I/O, no LLM calls, no external dependencies.
    """

    _CITATION_PATTERN: ClassVar[re.Pattern[str]] = re.compile(r"\[\d+(?:,\s*\d+)*\]")
    """Matches citation markers like [1], [2,3], [1,2,3]."""

    @staticmethod
    def _normalize(answer: str) -> str:
        """Strip whitespace, lowercase, remove citation markers like ``[1]``."""
        text = answer.strip().lower()
        text = AnswerVoter._CITATION_PATTERN.sub("", text).strip()
        return text

    @staticmethod
    def _is_similar(a: str, b: str) -> bool:
        """Return ``True`` when two normalized answers are similar enough to group."""
        ratio = difflib.SequenceMatcher(None, a, b).ratio()
        return ratio > _SIMILARITY_THRESHOLD

    @staticmethod
    def _group_similar(answers: list[str]) -> list[list[str]]:
        """Group answers by similarity into clusters.

        Each group contains the **original** answers that are similar
        (not the normalized versions).
        """
        normalized: list[tuple[str, str]] = [
            (orig, AnswerVoter._normalize(orig)) for orig in answers
        ]
        groups: list[list[tuple[str, str]]] = []

        for orig, norm in normalized:
            placed = False
            for group in groups:
                # Compare against the first element's normalized text
                if AnswerVoter._is_similar(norm, group[0][1]):
                    group.append((orig, norm))
                    placed = True
                    break
            if not placed:
                groups.append([(orig, norm)])

        # Discard normalized texts; return only original strings
        return [[pair[0] for pair in g] for g in groups]

    def vote(self, answers: list[str]) -> VoteResult:
        """Run answer voting across multiple rollouts and return the result.

        Parameters
        ----------
        answers:
            Raw answer strings from each rollout (may contain citation markers).

        Returns
        -------
        VoteResult with consensus, winner, confidence, vote counts, and candidates.

        Edge cases
        ----------
        - Empty list → ``VoteResult(consensus=False, confidence=NONE)``
        - Single answer → winner with ``HIGH`` confidence
        - Tie → ``consensus=False``, ``confidence=LOW``, candidates populated
        """
        if not answers:
            return VoteResult(
                consensus=False,
                winner_answer=None,
                confidence=ConfidenceLevel.NONE,
                vote_counts={},
                candidates=[],
            )

        if len(answers) == 1:
            norm = self._normalize(answers[0])
            return VoteResult(
                consensus=True,
                winner_answer=answers[0],
                confidence=ConfidenceLevel.HIGH,
                vote_counts={norm: 1},
                candidates=[],
            )

        groups = self._group_similar(answers)
        # Sort groups by size descending, then by index in original list for stability
        groups.sort(key=lambda g: (-len(g), answers.index(g[0])))

        vote_counts: dict[str, int] = {}
        for group in groups:
            norm = self._normalize(group[0])
            vote_counts[norm] = len(group)

        largest_group = groups[0]
        runner_up_size = len(groups[1]) if len(groups) > 1 else 0
        largest_size = len(largest_group)

        # — Check for tie between the two largest groups —
        if largest_size == runner_up_size:
            tied_groups: list[list[str]] = []
            for g in groups:
                if len(g) == largest_size:
                    tied_groups.append(g)
            candidates = [g[0] for g in tied_groups]
            return VoteResult(
                consensus=False,
                winner_answer=None,
                confidence=ConfidenceLevel.LOW,
                vote_counts=vote_counts,
                candidates=candidates,
            )

# — Winner found —
        winner_answer = largest_group[0]
        confidence = (
            ConfidenceLevel.HIGH
            if largest_size >= _CONSENSUS_WINNER_MIN_VOTES
            else ConfidenceLevel.MEDIUM
        )

        return VoteResult(
            consensus=True,
            winner_answer=winner_answer,
            confidence=confidence,
            vote_counts=vote_counts,
            candidates=[],
        )
