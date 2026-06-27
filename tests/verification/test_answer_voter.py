"""Tests for answer voter."""

from __future__ import annotations

from browser_goat.models import ConfidenceLevel
from browser_goat.verification.answer_voter import AnswerVoter


class TestNormalizeAnswer:
    def test_strips_whitespace_and_lowercases(self) -> None:
        assert AnswerVoter._normalize_answer("  Hello World  ") == "hello world"

    def test_normalized_keys_are_exact_duplicates(self) -> None:
        """Same text with different casing/whitespace produces same key."""
        a = AnswerVoter._normalize_answer("Paris is the capital.")
        b = AnswerVoter._normalize_answer("  PARIS IS THE CAPITAL.  ")
        assert a == b == "paris is the capital."


class TestVote:
    def test_unanimous_answers_returns_consensus(self) -> None:
        voter = AnswerVoter()
        result = voter.vote([
            "Paris is the capital of France.",
            "Paris is the capital of France.",
            "Paris is the capital of France.",
            "Paris is the capital of France.",
        ])
        assert result.consensus is True
        assert result.winner_answer is not None
        assert "Paris" in result.winner_answer
        assert result.confidence == ConfidenceLevel.HIGH
        assert result.candidates == []

    def test_majority_agreement_returns_majority_answer(self) -> None:
        voter = AnswerVoter()
        result = voter.vote([
            "Python is a programming language.",
            "Python is a programming language.",
            "Python is a programming language.",
            "Java is a programming language.",
        ])
        assert result.winner_answer is not None
        assert "Python" in result.winner_answer
        assert result.confidence == ConfidenceLevel.MEDIUM
        # 3 votes < early_stop_threshold (4) → no consensus
        assert result.consensus is False

    def test_tie_returns_no_consensus_and_candidates(self) -> None:
        voter = AnswerVoter()
        result = voter.vote([
            "Apples are fruits.",
            "Apples are fruits.",
            "Oranges are citrus.",
            "Oranges are citrus.",
        ])
        assert result.consensus is False
        assert result.winner_answer is None
        assert result.confidence == ConfidenceLevel.LOW
        assert len(result.candidates) == 2  # tied groups

    def test_empty_list_handles_gracefully(self) -> None:
        voter = AnswerVoter()
        result = voter.vote([])
        assert result.consensus is False
        assert result.winner_answer is None
        assert result.confidence == ConfidenceLevel.NONE
        assert result.candidates == []

    def test_single_candidate_returns_winner(self) -> None:
        voter = AnswerVoter()
        result = voter.vote(["The only answer."])
        assert result.consensus is True
        assert result.winner_answer == "The only answer."
        assert result.confidence == ConfidenceLevel.HIGH

    def test_all_different_answers_no_consensus(self) -> None:
        voter = AnswerVoter()
        result = voter.vote([
            "Apples are fruits.",
            "Python is a language.",
            "Quantum computing is hard.",
        ])
        assert result.consensus is False
        assert result.winner_answer is None

    def test_high_confidence_with_four_plus_majority(self) -> None:
        voter = AnswerVoter()
        result = voter.vote([
            "Paris is the capital.",
            "Paris is the capital.",
            "Paris is the capital.",
            "Paris is the capital.",
            "London is the capital.",
        ])
        assert result.consensus is True
        assert result.confidence == ConfidenceLevel.HIGH  # 4 >= threshold
        assert "Paris" in result.winner_answer  # type: ignore[operator]

    def test_vote_counts_reflect_groups(self) -> None:
        voter = AnswerVoter()
        result = voter.vote([
            "The capital of France is Paris.",
            "The capital of France is Paris.",
            "The capital of France is Paris.",
            "Quantum computing is a field of physics.",
        ])
        assert sum(result.vote_counts.values()) == 4
        assert "the capital of france is paris." in result.vote_counts
        assert "quantum computing is a field of physics." in result.vote_counts

    def test_four_identical_triggers_consensus(self) -> None:
        """4 identical answers reach the default early_stop_threshold."""
        voter = AnswerVoter()
        result = voter.vote([
            "Yes",
            "Yes",
            "Yes",
            "Yes",
        ])
        assert result.consensus is True
        assert result.confidence == ConfidenceLevel.HIGH
        assert result.winner_answer == "Yes"

    def test_three_identical_no_consensus_with_default_threshold(self) -> None:
        """3 identical answers fall short of default early_stop_threshold=4."""
        voter = AnswerVoter()
        result = voter.vote([
            "Yes",
            "Yes",
            "Yes",
        ])
        assert result.consensus is False
        assert result.confidence == ConfidenceLevel.MEDIUM
        assert result.winner_answer == "Yes"

    def test_custom_early_stop_threshold(self) -> None:
        """early_stop_threshold=2 means 2 votes trigger consensus."""
        voter = AnswerVoter(early_stop_threshold=2)
        result = voter.vote([
            "Yes",
            "Yes",
            "No",
        ])
        assert result.consensus is True
        assert result.confidence == ConfidenceLevel.HIGH
        assert result.winner_answer == "Yes"
