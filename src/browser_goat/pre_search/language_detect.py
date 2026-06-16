"""Language-aware search parameter detection — ported from Tongyi-DeepResearch tool_search.py.

Detects CJK characters in queries to set appropriate location/gl/hl
parameters for SearXNG search.
"""

from __future__ import annotations

from browser_goat.models import LanguageParams


def _contains_cjk(text: str) -> bool:
    """Check if text contains any CJK (Chinese/Japanese/Korean) characters.

    Uses Unicode range check for CJK Unified Ideographs (U+4E00–U+9FFF).
    Ported from Tongyi-DeepResearch inference/tool_search.py:42-44.
    """
    return any("\u4E00" <= char <= "\u9FFF" for char in text)


def _contains_japanese(text: str) -> bool:
    """Check if text contains Japanese-specific characters (Hiragana/Katakana)."""
    hiragana = any("\u3040" <= char <= "\u309F" for char in text)
    katakana = any("\u30A0" <= char <= "\u30FF" for char in text)
    return hiragana or katakana


def _contains_korean(text: str) -> bool:
    """Check if text contains Korean Hangul characters."""
    return any("\uAC00" <= char <= "\uD7AF" for char in text)


def detect_language_params(query: str) -> LanguageParams:
    """Detect language from query and return appropriate search parameters.

    If CJK characters detected:
        location=China, gl=cn, hl=zh-cn
    If Japanese detected:
        location=Japan, gl=jp, hl=ja
    If Korean detected:
        location=South Korea, gl=kr, hl=ko
    Otherwise:
        location=United States, gl=us, hl=en

    Args:
        query: The raw search query string.

    Returns:
        LanguageParams with appropriate location/gl/hl values.
    """
    if _contains_japanese(query):
        return LanguageParams(location="Japan", gl="jp", hl="ja")

    if _contains_korean(query):
        return LanguageParams(location="South Korea", gl="kr", hl="ko")

    if _contains_cjk(query):
        return LanguageParams(location="China", gl="cn", hl="zh-cn")

    # Default: English / United States
    return LanguageParams(location="United States", gl="us", hl="en")


def get_search_engines_for_language(params: LanguageParams) -> list[str]:
    """Return recommended search engines based on detected language.

    Different regions have different optimal engine combinations.
    """
    if params.gl == "cn":
        return ["google", "bing", "baidu"]
    elif params.gl == "jp":
        return ["google", "bing"]
    elif params.gl == "kr":
        return ["google", "bing", "naver"]
    else:
        return ["google", "bing"]
