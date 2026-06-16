"""Tests for Pydantic models."""

from __future__ import annotations

from browser_goat.models import (
    BrowserProfile,
    CleanedResult,
    ExtractedContent,
    ExtractedSource,
    FetchResult,
    GoalOrientedResult,
    LanguageParams,
    QualityResult,
    QueryAnalysis,
    QueryComplexity,
    QueryIntent,
    RankedResult,
    RawSearchResult,
    ReliabilityInfo,
    SearchRequest,
    SearchResult,
    SearxNGSearchParams,
)


class TestQueryIntent:
    def test_all_intents_are_valid(self) -> None:
        intents = list(QueryIntent)
        assert len(intents) == 6
        assert QueryIntent.FACTUAL in intents
        assert QueryIntent.RESEARCH in intents

    def test_intent_from_string(self) -> None:
        assert QueryIntent("research") == QueryIntent.RESEARCH
        assert QueryIntent("factual") == QueryIntent.FACTUAL


class TestQueryAnalysis:
    def test_default_values(self) -> None:
        analysis = QueryAnalysis(intent=QueryIntent.FACTUAL)
        assert analysis.is_time_sensitive is False
        assert analysis.entities == []
        assert analysis.complexity == QueryComplexity.MEDIUM
        assert analysis.optimal_sources == 15
        assert analysis.news_boost is False

    def test_research_query(self) -> None:
        analysis = QueryAnalysis(
            intent=QueryIntent.RESEARCH,
            is_time_sensitive=True,
            entities=["CRISPR", "gene therapy"],
            complexity=QueryComplexity.COMPLEX,
            optimal_sources=30,
            news_boost=False,
        )
        assert analysis.intent == QueryIntent.RESEARCH
        assert len(analysis.entities) == 2


class TestBrowserProfile:
    def test_profile_creation(self) -> None:
        profile = BrowserProfile(
            name="Chrome 147 Windows",
            user_agent="Mozilla/5.0...",
            sec_ch_ua='"Chromium";v="147"',
            sec_ch_ua_platform='"Windows"',
            sec_ch_ua_mobile="?0",
        )
        assert profile.name == "Chrome 147 Windows"


class TestLanguageParams:
    def test_default_english(self) -> None:
        params = LanguageParams()
        assert params.location == "United States"
        assert params.gl == "us"
        assert params.hl == "en"

    def test_chinese_params(self) -> None:
        params = LanguageParams(location="China", gl="cn", hl="zh-cn")
        assert params.gl == "cn"


class TestRawSearchResult:
    def test_minimal_result(self) -> None:
        result = RawSearchResult(url="https://example.com")
        assert result.title == ""
        assert result.content == ""
        assert result.engine == ""

    def test_full_result(self) -> None:
        result = RawSearchResult(
            title="Example",
            url="https://example.com",
            content="A great website",
            engine="google",
            score=0.85,
            category="general",
        )
        assert result.score == 0.85


class TestCleanedResult:
    def test_extends_raw_result(self) -> None:
        result = CleanedResult(
            url="https://example.com",
            normalized_url="https://example.com/path",
            is_duplicate=False,
        )
        assert result.normalized_url == "https://example.com/path"


class TestRankedResult:
    def test_ranking_scores(self) -> None:
        result = RankedResult(
            url="https://example.com",
            normalized_url="https://example.com/path",
            rrf_score=0.8,
            bm25_score=0.6,
            mmr_score=0.7,
            final_score=0.75,
            rank=1,
        )
        assert result.rank == 1
        assert result.final_score == 0.75


class TestFetchResult:
    def test_successful_fetch(self) -> None:
        result = FetchResult(
            url="https://example.com",
            html="<html>...</html>",
            status_code=200,
            success=True,
            used_scrapling=True,
            fetch_tier=2,
            latency_ms=150,
        )
        assert result.success is True
        assert result.used_scrapling is True

    def test_failed_fetch(self) -> None:
        result = FetchResult(
            url="https://blocked.com",
            success=False,
            error="403 Forbidden",
        )
        assert result.success is False
        assert result.error == "403 Forbidden"


class TestExtractedContent:
    def test_basic_extraction(self) -> None:
        content = ExtractedContent(
            url="https://example.com",
            title="Example Article",
            text="Full article text here.",
            extraction_tier=3,
            word_count=4,
        )
        assert content.extraction_tier == 3


class TestGoalOrientedResult:
    def test_extends_extracted_content(self) -> None:
        result = GoalOrientedResult(
            url="https://example.com",
            title="Article",
            text="Full text.",
            extraction_tier=3,
            rational="This page answers the query because...",
            evidence="The page states that...",
            summary="A summary of the page.",
        )
        assert result.rational != ""
        assert result.evidence != ""
        assert result.summary != ""


class TestQualityResult:
    def test_passed(self) -> None:
        result = QualityResult(passed=True)
        assert result.passed is True
        assert result.reason is None

    def test_failed_short_answer(self) -> None:
        result = QualityResult(passed=False, reason="answer_too_short", retries_used=1)
        assert result.passed is False
        assert result.retries_used == 1


class TestReliabilityInfo:
    def test_default_all_good(self) -> None:
        info = ReliabilityInfo()
        assert info.give_up_detected is False
        assert info.quality_passed is True
        assert info.force_answer_used is False


class TestExtractedSource:
    def test_full_source(self) -> None:
        source = ExtractedSource(
            url="https://example.com",
            title="Article",
            rational="Relevant because...",
            evidence="The evidence is...",
            summary="Summary text.",
            extraction_tier=3,
            used_scrapling=True,
            rank=1,
            final_score=0.85,
            engine="google",
        )
        assert source.rank == 1
        assert source.used_scrapling is True


class TestSearchResult:
    def test_minimal_result(self) -> None:
        result = SearchResult(answer="Paris is the capital of France.")
        assert result.answer == "Paris is the capital of France."
        assert result.sources == []

    def test_full_result(self) -> None:
        result = SearchResult(
            answer="Paris is the capital. [1]",
            sources=[
                ExtractedSource(
                    url="https://en.wikipedia.org/wiki/Paris",
                    title="Paris - Wikipedia",
                    rational="Primary source.",
                    evidence="Paris is the capital...",
                    summary="Paris is the capital of France.",
                    extraction_tier=2,
                    used_scrapling=False,
                    rank=1,
                    final_score=0.9,
                    engine="wikipedia",
                )
            ],
            query_intent=QueryIntent.FACTUAL,
            engines_used=["google", "wikipedia"],
            total_sources_found=15,
            total_sources_used=1,
            extraction_success_rate=0.93,
            pipeline_latency_ms=1200,
        )
        assert len(result.sources) == 1
        assert result.query_intent == QueryIntent.FACTUAL
        assert result.engines_used == ["google", "wikipedia"]


class TestSearchRequest:
    def test_minimal_request(self) -> None:
        req = SearchRequest(query="What is Python?")
        assert req.query == "What is Python?"
        assert req.max_sources == 15
        assert req.reliability_mode == "standard"

    def test_full_request(self) -> None:
        req = SearchRequest(
            query="Latest AI research",
            engines=["google", "scholar"],
            time_range="year",
            language="en",
            max_sources=20,
            reliability_mode="high",
        )
        assert req.reliability_mode == "high"


class TestSearxNGSearchParams:
    def test_default_params(self) -> None:
        params = SearxNGSearchParams(query="test")
        assert params.query == "test"
        assert params.engines == ["google", "bing"]
        assert params.language == "en"
        assert params.pageno == 1
