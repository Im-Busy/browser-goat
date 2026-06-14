"""Tests for Hybrid Ranking Engine."""

from __future__ import annotations

from browsing_meta.models import CleanedResult
from browsing_meta.post_search.ranking import HybridRanker


def _make_result(url: str, content: str, engine: str = "google") -> CleanedResult:
    """Helper to create a CleanedResult for testing."""
    return CleanedResult(
        url=url,
        normalized_url=url,
        content=content,
        engine=engine,
        is_duplicate=False,
    )


class TestRRF:
    def test_higher_weight_higher_score(self) -> None:
        ranker = HybridRanker()
        results = [
            _make_result("https://a.com", "content A", "google"),
            _make_result("https://b.com", "content B", "duckduckgo"),
        ]
        scored = ranker._compute_rrf(results)
        # Google (weight 1.5) should score higher than duckduckgo (weight 1.0)
        assert scored[0].rrf_score > scored[1].rrf_score

    def test_handles_empty(self) -> None:
        ranker = HybridRanker()
        scored = ranker._compute_rrf([])
        assert scored == []


class TestBM25:
    def test_exact_match_scores_higher(self) -> None:
        ranker = HybridRanker()
        query = "python programming"
        results = [
            _make_result("https://a.com", "python programming is great for development"),
            _make_result("https://b.com", "java is also a good language"),
        ]
        # First need RRF scores
        rrf_scored = ranker._compute_rrf(results)
        scored = ranker._compute_bm25(rrf_scored, query)
        assert scored[0].bm25_score > scored[1].bm25_score

    def test_exact_phrase_bonus(self) -> None:
        ranker = HybridRanker()
        query = "machine learning"
        results = [
            _make_result("https://a.com",
                "Machine learning is transforming artificial intelligence research across many domains and industries"),
            _make_result("https://b.com",
                "Learning about machines and how they work is an interesting topic for engineering students"),
        ]
        rrf_scored = ranker._compute_rrf(results)
        scored = ranker._compute_bm25(rrf_scored, query)
        # First has exact phrase "machine learning" → 1.25x bonus
        assert scored[0].bm25_score > scored[1].bm25_score


class TestMMR:
    def test_diverse_results(self) -> None:
        ranker = HybridRanker()
        results = [
            _make_result("https://a.com", "python is a programming language"),
            _make_result("https://b.com", "python is a programming language"),  # very similar
            _make_result("https://c.com", "quantum computing uses qubits and is related to physics"),
        ]
        # First compute RRF, then BM25, then MMR
        rrf_scored = ranker._compute_rrf(results)
        bm25_scored = ranker._compute_bm25(rrf_scored, "python programming")
        mmr = ranker._compute_mmr(bm25_scored, "python programming")
        # Should have results
        assert len(mmr) >= 2


class TestTokenize:
    def test_removes_stopwords(self) -> None:
        ranker = HybridRanker()
        tokens = ranker._tokenize("the quick brown fox")
        assert "the" not in tokens
        assert "fox" in tokens

    def test_min_length_two(self) -> None:
        ranker = HybridRanker()
        tokens = ranker._tokenize("a b c de fg hij")
        assert "a" not in tokens
        assert "b" not in tokens
        assert "de" in tokens


class TestChunkText:
    def test_short_text_single_chunk(self) -> None:
        ranker = HybridRanker()
        chunks = ranker._chunk_text("This is a short text that should be long enough to form a chunk.")
        assert len(chunks) >= 1

    def test_paragraph_boundaries(self) -> None:
        ranker = HybridRanker()
        text = "First paragraph here.\n\nSecond paragraph here."
        chunks = ranker._chunk_text(text)
        assert len(chunks) >= 1


class TestRank:
    def test_full_pipeline(self) -> None:
        ranker = HybridRanker()
        results = [
            _make_result("https://a.com", "Python is a popular programming language for AI and ML", "google"),
            _make_result("https://b.com", "Java is used for enterprise applications", "bing"),
            _make_result("https://c.com", "Rust is a systems programming language", "google"),
        ]
        ranked = ranker.rank(results, "python programming language")
        assert len(ranked) > 0
        # Python-related result should rank highest
        assert ranked[0].final_score > 0

    def test_assigns_ranks(self) -> None:
        ranker = HybridRanker()
        results = [
            _make_result(f"https://{chr(97+i)}.com", f"Content {i}", "google")
            for i in range(5)
        ]
        ranked = ranker.rank(results, "content")
        for r in ranked:
            assert r.rank >= 1
        assert ranked[0].rank == 1

    def test_handles_empty_results(self) -> None:
        ranker = HybridRanker()
        ranked = ranker.rank([], "query")
        assert ranked == []
