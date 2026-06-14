"""Give-Up Detector — detect agent failure language.

43 regex patterns (English + Chinese) for detecting "I can't answer"
language in LLM responses. Ported from Marco-DeepResearch context_manager.py.
"""

from __future__ import annotations

import re

from browsing_meta.models import GiveUpResult

# ── Give-Up Patterns ──────────────────────────────────────────────────────────

# English patterns: 30+ regexes matching failure/uncertainty language
GIVE_UP_PATTERNS_EN: list[str] = [
    r"I (couldn't|could not|can't|cannot|am unable to) find",
    r"I (couldn't|could not|can't|cannot|am unable to) (determine|locate|identify)",
    r"I (couldn't|could not|can't|cannot) (answer|provide|give)",
    r"(no|zero|0) (results|matches|information|data|relevant) (found|available|returned)",
    r"unable to (find|determine|locate|identify|answer|provide|retrieve|access|verify|confirm)",
    r"insufficient (information|data|results|evidence|context|details)",
    r"(does not|doesn't|don't) (contain|provide|include|have|mention)",
    r"(sorry|unfortunately|regrettably).{0,30}(couldn't|could not|can't|cannot|unable)",
    r"(not|wasn't|were not) able to (find|locate|determine|identify|answer)",
    r"(no|without) (access|way|method) to",
    r"search (returned|yielded|produced) (no|zero|nothing)",
    r"(limited|scarce|sparse|little|not enough) (information|data|results)",
    r"(failed|failure) to (find|retrieve|obtain|get|access)",
    r"(did not|didn't) (find|return|yield|produce|show)",
    r"(nothing|not much|very little|little) (relevant|useful|helpful)",
    r"(beyond|outside) (my|our) (knowledge|capability|scope|training)",
    r"(I|we) (do not|don't) (know|have|possess)",
    r"(cannot|can't) (confirm|verify|validate|corroborate)",
    r"(no|not) (conclusive|definitive|clear|specific) (answer|result|information)",
    r"the (search|query|results) (did not|didn't|does not|doesn't)",
    r"(based on|according to) (the|my|our) (search|available|current)",
    r"it (appears|seems) (that )?(there (is|are) (no|not|insufficient)|the)",
    r"(inconclusive|ambiguous|unclear|uncertain|indeterminate)",
    r"more (research|information|data|context|details) (is |are )?(needed|required|necessary)",
    r"(speculative|not certain|unable to say|hard to say|difficult to (say|determine))",
    r"could not (be )?(found|located|determined|verified|confirmed|established)",
    r"(lack|absence|lacking) of (information|data|evidence|results|details)",
    r"(empty|blank|void) (result|response|answer)",
    r"(query|search term|request) (is |was )?(too|very) (broad|vague|ambiguous|general|unspecific)",
    r"(page|site|resource|URL|link) (not found|unavailable|inaccessible|down|offline|404)",
]

# Chinese patterns: 13+ regexes matching failure/uncertainty language
GIVE_UP_PATTERNS_ZH: list[str] = [
    r"无法(找到|确定|回答|提供|获取|访问|验证|确认)",
    r"没有(找到|发现|相关|足够|明确|具体)",
    r"未能(找到|获取|检索|确定|回答)",
    r"搜索(结果|到|出).{0,10}(没有|为零|为空)",
    r"信息(不足|不够|有限|缺乏|稀少)",
    r"(抱歉|遗憾|对不起).{0,20}(无法|不能|没有)",
    r"不(能|可以|确定|清楚)",
    r"(缺乏|缺少|不足).{0,5}(信息|数据|资料|证据)",
    r"无法(访问|连接|打开)",
    r"(找不到|查不到|搜不到)",
    r"(未|没)(发现|检索到|查询到|获取到)",
    r"(不确定|不清楚|无法判断)",
    r"需要(更多|进一步)(的)?(信息|研究|调查|数据)",
]


class GiveUpDetector:
    """Detect when an LLM answer indicates failure to answer the query.

    Uses 43 regex patterns (EN + ZH) to detect give-up language.
    Ported from Marco-DeepResearch marco/agent/context_manager.py.
    """

    def __init__(self) -> None:
        self._en_patterns = [re.compile(p, re.IGNORECASE) for p in GIVE_UP_PATTERNS_EN]
        self._zh_patterns = [re.compile(p) for p in GIVE_UP_PATTERNS_ZH]

    def detect(self, text: str) -> GiveUpResult:
        """Check if text contains give-up language.

        Args:
            text: The answer text to check.

        Returns:
            GiveUpResult with detection status and matched pattern.
        """
        if not text:
            return GiveUpResult(detected=True, pattern_matched="empty_answer", language="en")

        # Check English patterns
        for pattern in self._en_patterns:
            match = pattern.search(text)
            if match:
                return GiveUpResult(
                    detected=True,
                    pattern_matched=pattern.pattern,
                    language="en",
                )

        # Check Chinese patterns
        for pattern in self._zh_patterns:
            match = pattern.search(text)
            if match:
                return GiveUpResult(
                    detected=True,
                    pattern_matched=pattern.pattern,
                    language="zh",
                )

        return GiveUpResult(detected=False, language="en")
