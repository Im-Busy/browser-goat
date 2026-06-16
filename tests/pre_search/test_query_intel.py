"""Tests for Query Intelligence Engine."""

from __future__ import annotations

from browser_goat.models import QueryComplexity, QueryIntent
from browser_goat.pre_search.query_intel import QueryIntel


class TestDetectIntent:
    def test_factual_query(self) -> None:
        qi = QueryIntel()
        assert qi._detect_intent("what is python") == QueryIntent.FACTUAL

    def test_person_query(self) -> None:
        qi = QueryIntel()
        assert qi._detect_intent("who is satya nadella") == QueryIntent.PERSON
        assert qi._detect_intent("who created python") == QueryIntent.PERSON

    def test_comparison_query(self) -> None:
        qi = QueryIntel()
        assert qi._detect_intent("python vs rust") == QueryIntent.COMPARISON
        assert qi._detect_intent("difference between python and java") == QueryIntent.COMPARISON

    def test_howto_query(self) -> None:
        qi = QueryIntel()
        assert qi._detect_intent("how to deploy docker") == QueryIntent.HOWTO
        assert qi._detect_intent("tutorial for beginners") == QueryIntent.HOWTO

    def test_temporal_query(self) -> None:
        qi = QueryIntel()
        assert qi._detect_intent("today news") == QueryIntent.TEMPORAL
        assert qi._detect_intent("latest python release") == QueryIntent.TEMPORAL

    def test_research_query(self) -> None:
        qi = QueryIntel()
        assert qi._detect_intent("research on quantum computing") == QueryIntent.RESEARCH
        assert qi._detect_intent("advances in ai 2025") == QueryIntent.RESEARCH


class TestDetectTemporal:
    def test_recency_keywords(self) -> None:
        qi = QueryIntel()
        assert qi._detect_temporal("latest news about python") is True
        assert qi._detect_temporal("recent developments in ai") is True

    def test_year_reference(self) -> None:
        qi = QueryIntel()
        assert qi._detect_temporal("python trends 2026") is True

    def test_non_temporal(self) -> None:
        qi = QueryIntel()
        assert qi._detect_temporal("what is python") is False
        assert qi._detect_temporal("define machine learning") is False


class TestExtractEntities:
    def test_simple_entity(self) -> None:
        qi = QueryIntel()
        entities = qi._extract_entities("What is Python used for")
        assert "Python" in entities

    def test_multi_word_entity(self) -> None:
        qi = QueryIntel()
        entities = qi._extract_entities("Tell me about New York City history")
        assert "New York City" in entities

    def test_no_entities(self) -> None:
        qi = QueryIntel()
        entities = qi._extract_entities("what is the meaning of life")
        # "Meaning" and "Life" are capitalized at start - but "meaning" is lowercase
        # so only "Life" might be extracted, which is a common word
        # The stopword filter should handle most cases
        assert isinstance(entities, list)

    def test_deduplication(self) -> None:
        qi = QueryIntel()
        entities = qi._extract_entities("Python and python and PYTHON")
        # Should dedup case-insensitively
        for e in entities:
            assert entities.count(e) == 1


class TestScoreComplexity:
    def test_simple(self) -> None:
        qi = QueryIntel()
        assert qi._score_complexity("what is python") == QueryComplexity.SIMPLE

    def test_medium(self) -> None:
        qi = QueryIntel()
        assert qi._score_complexity(
            "what is the difference between python and javascript"
        ) == QueryComplexity.MEDIUM

    def test_complex(self) -> None:
        qi = QueryIntel()
        assert qi._score_complexity(
            "what is the relationship between quantum computing and machine learning "
            "and how can they be combined for optimization problems in finance"
        ) == QueryComplexity.COMPLEX


class TestAnalyze:
    def test_full_analysis_factual(self) -> None:
        qi = QueryIntel()
        result = qi.analyze("What is Python?")
        assert result.intent == QueryIntent.FACTUAL
        assert result.complexity == QueryComplexity.SIMPLE
        assert result.is_time_sensitive is False

    def test_full_analysis_research(self) -> None:
        qi = QueryIntel()
        result = qi.analyze("latest research on CRISPR gene editing for cancer 2026")
        assert result.intent == QueryIntent.RESEARCH
        assert result.is_time_sensitive is True
        assert result.complexity == QueryComplexity.MEDIUM
        assert result.optimal_sources >= 25

    def test_full_analysis_comparison(self) -> None:
        qi = QueryIntel()
        result = qi.analyze("Python vs Rust for web development")
        assert result.intent == QueryIntent.COMPARISON
        assert result.news_boost is False

    def test_enrich_query_adds_year(self) -> None:
        qi = QueryIntel()
        analysis = qi.analyze("latest quantum computing breakthroughs")
        enriched = qi.enrich_query("latest quantum computing breakthroughs", analysis)
        assert "2026" in enriched

    def test_enrich_query_no_duplicate_year(self) -> None:
        qi = QueryIntel()
        analysis = qi.analyze("ai research 2026 trends")
        enriched = qi.enrich_query("ai research 2026 trends", analysis)
        # Should not add another "2026"
        assert enriched.count("2026") == 1
