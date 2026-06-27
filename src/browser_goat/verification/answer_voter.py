"""Pure-logic answer voting for multi-rollout verification.

Groups answers by exact normalized text match via Counter,
and returns a VoteResult with confidence level and consensus status.
"""

from __future__ import annotations

from collections import Counter

from browser_goat.models import ConfidenceLevel, VoteResult


class AnswerVoter:
    """Groups identical normalized answers and returns voting results.

    Pure synchronous logic — no I/O, no LLM calls, no external dependencies.
    """

    def __init__(self, early_stop_threshold: int = 4) -> None:
        self.early_stop_threshold = early_stop_threshold

    @staticmethod
    def _normalize_answer(text: str) -> str:
        """Strip whitespace and lowercase for exact-match grouping."""
        return text.strip().lower()

    def vote(self, answers: list[str]) -> VoteResult:
        """Run answer voting across multiple rollouts and return the result.

        Parameters
        ----------
        answers:
            Raw answer strings from each rollout.

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
            return VoteResult(
                consensus=True,
                winner_answer=answers[0],
                confidence=ConfidenceLevel.HIGH,
                vote_counts={self._normalize_answer(answers[0]): 1},
                candidates=[],
            )

        counter: Counter[str] = Counter()
        norm_to_raw: dict[str, str] = {}
        for ans in answers:
            key = self._normalize_answer(ans)
            counter[key] += 1
            if key not in norm_to_raw:
                norm_to_raw[key] = ans

        max_count = counter.most_common(1)[0][1]
        top_keys = [k for k, c in counter.items() if c == max_count]

        if len(top_keys) == 1:
            # Single winner
            winner_key = top_keys[0]
            raw_answers = [a for a in answers if self._normalize_answer(a) == winner_key]
            consensus = len(raw_answers) >= self.early_stop_threshold
            return VoteResult(
                consensus=consensus,
                winner_answer=norm_to_raw[winner_key],
                confidence=ConfidenceLevel.HIGH if consensus else ConfidenceLevel.MEDIUM,
                vote_counts=dict(counter),
                candidates=[],
            )

        # Tie between multiple top-voted answers
        return VoteResult(
            consensus=False,
            winner_answer=None,
            confidence=ConfidenceLevel.LOW,
            vote_counts=dict(counter),
            candidates=[norm_to_raw[k] for k in top_keys],
        )
