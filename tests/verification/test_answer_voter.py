"""Tests for answer voter."""

from __future__ import annotations

from browsing_meta.models import ConfidenceLevel
from browsing_meta.verification.answer_voter import AnswerVoter


class TestNormalize:
    def test_strips_whitespace_and_lowercases(self) -> None:
        assert AnswerVoter._normalize("  Hello World  ") == "hello world"

    def test_removes_citation_markers(self) -> None:
        assert AnswerVoter._normalize("Paris is the capital [1].") == "paris is the capital ."

    def test_removes_multiple_citations(self) -> None:
        norm = AnswerVoter._normalize("The answer is 42 [1,2,3] according to [4].")
        assert "[" not in norm


class TestIsSimilar:
    def test_identical_texts(self) -> None:
        assert AnswerVoter._is_similar("hello world", "hello world") is True

    def test_slightly_different_texts(self) -> None:
        assert AnswerVoter._is_similar("Paris is the capital of France.", "Paris is the capital of France [1].") is True

    def test_very_different_texts(self) -> None:
        assert AnswerVoter._is_similar("apples are fruits", "quantum computing is hard") is False

    def test_citation_difference(self) -> None:
        assert AnswerVoter._is_similar(
            "Paris is the capital [1].",
            "Paris is the capital [2,3].",
        ) is True


class TestGroupSimilar:
    def test_groups_identical_answers(self) -> None:
        groups = AnswerVoter._group_similar(["a", "a", "a"])
        assert len(groups) == 1
        assert len(groups[0]) == 3

    def test_separates_different_answers(self) -> None:
        groups = AnswerVoter._group_similar(["apples", "quantum computing"])
        assert len(groups) == 2

    def test_preserves_original_strings(self) -> None:
        groups = AnswerVoter._group_similar(["Hello [1]", "hello [2]"])
        assert len(groups) == 1
        # Original strings with citations preserved
        assert "[1]" in groups[0][0]
        assert "[2]" in groups[0][1]


class TestVote:
    def test_unanimous_answers_returns_consensus(self) -> None:
        voter = AnswerVoter()
        result = voter.vote([
            "Paris is the capital of France. [1]",
            "Paris is the capital of France. [2]",
            "Paris is the capital of France. [3]",
            "Paris is the capital of France. [4]",
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
        assert result.consensus is True
        assert result.winner_answer is not None
        assert "Python" in result.winner_answer
        assert result.confidence == ConfidenceLevel.MEDIUM  # 3 votes < 4 threshold

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
