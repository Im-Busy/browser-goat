"""Tests for URL Pipeline."""

from __future__ import annotations

from browser_goat.models import RawSearchResult
from browser_goat.post_search.url_pipeline import URLPipeline


class TestNormalizeURL:
    def test_strips_utm_params(self) -> None:
        pipeline = URLPipeline()
        url = "https://example.com/page?utm_source=twitter&utm_medium=social&keep=this"
        normalized = pipeline._normalize_url(url)
        assert "utm_source" not in normalized
        assert "utm_medium" not in normalized
        assert "keep=this" in normalized

    def test_lowercases_hostname(self) -> None:
        pipeline = URLPipeline()
        url = "https://EXAMPLE.COM/Page"
        normalized = pipeline._normalize_url(url)
        assert "example.com" in normalized

    def test_removes_fragment(self) -> None:
        pipeline = URLPipeline()
        url = "https://example.com/page#section-2"
        normalized = pipeline._normalize_url(url)
        assert "#section-2" not in normalized

    def test_handles_malformed_url(self) -> None:
        pipeline = URLPipeline()
        url = "not a url"
        normalized = pipeline._normalize_url(url)
        assert normalized == url


class TestShouldSkip:
    def test_skips_pinterest(self) -> None:
        pipeline = URLPipeline()
        assert pipeline._should_skip("https://pinterest.com/pin/123") is True

    def test_skips_quora(self) -> None:
        pipeline = URLPipeline()
        assert pipeline._should_skip("https://www.quora.com/What-is-Python") is True

    def test_skips_pdf(self) -> None:
        pipeline = URLPipeline()
        assert pipeline._should_skip("https://example.com/report.pdf") is True

    def test_allows_normal_site(self) -> None:
        pipeline = URLPipeline()
        assert pipeline._should_skip("https://en.wikipedia.org/wiki/Python") is False

    def test_skips_subdomain_of_blocked(self) -> None:
        pipeline = URLPipeline()
        assert pipeline._should_skip("https://api.pinterest.com/v1/") is True


class TestProcess:
    def test_dedup_same_url(self) -> None:
        pipeline = URLPipeline()
        results = [
            RawSearchResult(url="https://example.com/page", engine="google"),
            RawSearchResult(url="https://example.com/page", engine="bing"),
        ]
        cleaned = pipeline.process(results)
        assert len(cleaned) == 2
        assert cleaned[0].is_duplicate is False
        assert cleaned[1].is_duplicate is True

    def test_blocks_skipped_domain(self) -> None:
        pipeline = URLPipeline()
        results = [
            RawSearchResult(url="https://pinterest.com/pin/123", engine="google"),
            RawSearchResult(url="https://example.com", engine="bing"),
        ]
        cleaned = pipeline.process(results)
        assert cleaned[0].blocked_reason is not None
        assert cleaned[1].blocked_reason is None

    def test_handles_empty_list(self) -> None:
        pipeline = URLPipeline()
        cleaned = pipeline.process([])
        assert cleaned == []


class TestDedupKey:
    def test_same_host_path_same_key(self) -> None:
        pipeline = URLPipeline()
        key1 = pipeline._dedup_key("https://example.com/page")
        key2 = pipeline._dedup_key("https://example.com/page")
        assert key1 == key2

    def test_different_host_different_key(self) -> None:
        pipeline = URLPipeline()
        key1 = pipeline._dedup_key("https://example.com/page")
        key2 = pipeline._dedup_key("https://other.com/page")
        assert key1 != key2
