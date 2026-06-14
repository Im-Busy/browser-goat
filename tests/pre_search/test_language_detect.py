"""Tests for language detection."""

from __future__ import annotations

from browsing_meta.pre_search.language_detect import (
    _contains_cjk,
    detect_language_params,
    get_search_engines_for_language,
)


class TestContainsCJK:
    def test_chinese_text(self) -> None:
        assert _contains_cjk("人工智能") is True

    def test_mixed_chinese_english(self) -> None:
        assert _contains_cjk("latest 人工智能 research") is True

    def test_english_only(self) -> None:
        assert _contains_cjk("artificial intelligence research") is False

    def test_empty_string(self) -> None:
        assert _contains_cjk("") is False

    def test_japanese_kana_only(self) -> None:
        # Hiragana/Katakana are NOT in CJK range
        assert _contains_cjk("こんにちは") is False

    def test_korean_hangul_only(self) -> None:
        # Hangul is NOT in CJK range
        assert _contains_cjk("안녕하세요") is False


class TestDetectLanguageParams:
    def test_english_default(self) -> None:
        params = detect_language_params("what is artificial intelligence")
        assert params.location == "United States"
        assert params.gl == "us"
        assert params.hl == "en"

    def test_chinese_query(self) -> None:
        params = detect_language_params("什么是人工智能")
        assert params.location == "China"
        assert params.gl == "cn"
        assert params.hl == "zh-cn"

    def test_mixed_query(self) -> None:
        params = detect_language_params("AI 人工智能 applications")
        assert params.location == "China"
        assert params.gl == "cn"

    def test_japanese_query(self) -> None:
        params = detect_language_params("人工知能とは")
        # "とは" is hiragana → Japanese check matches first → gl=jp
        assert params.gl in ("jp", "ja")

    def test_korean_query(self) -> None:
        params = detect_language_params("인공지능 연구")
        assert params.gl == "kr"
        assert params.hl == "ko"


class TestGetSearchEngines:
    def test_chinese_engines(self) -> None:
        from browsing_meta.models import LanguageParams
        params = LanguageParams(location="China", gl="cn", hl="zh-cn")
        engines = get_search_engines_for_language(params)
        assert "baidu" in engines

    def test_english_engines(self) -> None:
        from browsing_meta.models import LanguageParams
        params = LanguageParams()
        engines = get_search_engines_for_language(params)
        assert engines == ["google", "bing"]

    def test_korean_engines(self) -> None:
        from browsing_meta.models import LanguageParams
        params = LanguageParams(location="South Korea", gl="kr", hl="ko")
        engines = get_search_engines_for_language(params)
        assert "naver" in engines
