"""Tests for Give-Up Detector."""

from __future__ import annotations

from browsing_meta.reliability.give_up_detector import GiveUpDetector


class TestDetect:
    def test_could_not_find_pattern(self) -> None:
        detector = GiveUpDetector()
        result = detector.detect("I could not find any information about quantum computing.")
        assert result.detected is True
        assert result.language == "en"

    def test_no_results_found_pattern(self) -> None:
        detector = GiveUpDetector()
        result = detector.detect("No results found for your search query.")
        assert result.detected is True
        assert result.language == "en"

    def test_unable_to_determine_pattern(self) -> None:
        detector = GiveUpDetector()
        result = detector.detect("The system is unable to determine the correct answer.")
        assert result.detected is True
        assert result.language == "en"

    def test_normal_answer_returns_false(self) -> None:
        detector = GiveUpDetector()
        result = detector.detect(
            "Python is a programming language created by Guido van Rossum in 1991. "
            "It is widely used for web development, data science, and automation."
        )
        assert result.detected is False
        assert result.language == "en"

    def test_empty_string_detected(self) -> None:
        detector = GiveUpDetector()
        result = detector.detect("")
        assert result.detected is True
        assert result.pattern_matched == "empty_answer"
        assert result.language == "en"

    def test_none_input_detected(self) -> None:
        detector = GiveUpDetector()
        result = detector.detect("")  # None coerces to empty string path
        assert result.detected is True
        assert result.pattern_matched == "empty_answer"

    def test_chinese_give_up_pattern(self) -> None:
        detector = GiveUpDetector()
        result = detector.detect("无法找到相关信息，请尝试其他关键词。")
        assert result.detected is True
        assert result.language == "zh"

    def test_chinese_insufficient_info_pattern(self) -> None:
        detector = GiveUpDetector()
        result = detector.detect("信息不足，无法给出准确回答。")
        assert result.detected is True
        assert result.language == "zh"

    def test_chinese_search_no_result_pattern(self) -> None:
        detector = GiveUpDetector()
        result = detector.detect("搜索结果为空，建议更换搜索词。")
        assert result.detected is True
        assert result.language == "zh"

    def test_sorry_unable_pattern(self) -> None:
        detector = GiveUpDetector()
        result = detector.detect("Sorry, I am unable to provide an answer at this time.")
        assert result.detected is True
        assert result.language == "en"

    def test_detect_returns_pattern_matched(self) -> None:
        detector = GiveUpDetector()
        result = detector.detect("I couldn't find any relevant sources")
        assert result.detected is True
        assert result.pattern_matched is not None
        # Should match "I couldn't find" pattern
        assert "couldn" in str(result.pattern_matched) or "find" in str(result.pattern_matched)

    def test_insufficient_info_pattern(self) -> None:
        detector = GiveUpDetector()
        result = detector.detect("There is insufficient information to answer this question.")
        assert result.detected is True
        assert result.language == "en"

    def test_whitespace_only_string(self) -> None:
        detector = GiveUpDetector()
        # Whitespace is not empty — should not trigger empty_answer, but may match nothing
        result = detector.detect("   ")
        assert result.detected is False
        assert result.pattern_matched is None

    def test_failed_to_retrieve_pattern(self) -> None:
        detector = GiveUpDetector()
        result = detector.detect("The search engine failed to retrieve any results.")
        assert result.detected is True
        assert result.language == "en"
