"""Tests for SearXNG async client."""

from __future__ import annotations

from browser_goat.models import (
    BrowserProfile,
)
from browser_goat.searxng_client import SearXNGClient


class TestSearXNGClient:
    def test_init_default_url(self) -> None:
        client = SearXNGClient()
        assert client.base_url == "http://localhost:8080"

    def test_init_custom_url(self) -> None:
        client = SearXNGClient("http://searxng:9090")
        assert client.base_url == "http://searxng:9090"

    def test_init_strips_trailing_slash(self) -> None:
        client = SearXNGClient("http://localhost:8080/")
        assert client.base_url == "http://localhost:8080"


class TestBuildHeaders:
    def test_no_profile_returns_empty(self) -> None:
        client = SearXNGClient()
        headers = client._build_headers(None)
        assert headers == {}

    def test_profile_injects_all_headers(self) -> None:
        client = SearXNGClient()
        profile = BrowserProfile(
            name="Chrome 147",
            user_agent="Mozilla/5.0 Test",
            sec_ch_ua='"Chromium";v="147"',
            sec_ch_ua_platform='"Windows"',
            sec_ch_ua_mobile="?0",
        )
        headers = client._build_headers(profile)
        assert headers["User-Agent"] == "Mozilla/5.0 Test"
        assert headers["Sec-CH-UA"] == '"Chromium";v="147"'
        assert headers["Sec-CH-UA-Platform"] == '"Windows"'
        assert headers["Sec-CH-UA-Mobile"] == "?0"


class TestParseResults:
    def test_empty_data(self) -> None:
        client = SearXNGClient()
        results = client._parse_results({})
        assert results == []

    def test_no_results_key(self) -> None:
        client = SearXNGClient()
        results = client._parse_results({"query": "test"})
        assert results == []

    def test_valid_results(self) -> None:
        client = SearXNGClient()
        data = {
            "query": "python",
            "number_of_results": 2,
            "results": [
                {
                    "title": "Python.org",
                    "url": "https://python.org",
                    "content": "Python is a programming language.",
                    "engine": "google",
                    "score": 0.95,
                    "category": "general",
                    "parsed_url": ["https://python.org"],
                    "publishedDate": "2026-01-01",
                },
                {
                    "title": "Python Docs",
                    "url": "https://docs.python.org",
                    "content": "Documentation for Python.",
                    "engine": "bing",
                    "score": 0.85,
                    "category": "general",
                },
            ],
        }
        results = client._parse_results(data)
        assert len(results) == 2
        assert results[0].title == "Python.org"
        assert results[0].url == "https://python.org"
        assert results[0].engine == "google"
        assert results[0].score == 0.95
        assert results[1].engine == "bing"

    def test_skips_results_without_url(self) -> None:
        client = SearXNGClient()
        data = {
            "results": [
                {"title": "No URL", "content": "Missing url field"},
                {"title": "Has URL", "url": "https://example.com", "content": "Good"},
            ]
        }
        results = client._parse_results(data)
        assert len(results) == 1
        assert results[0].url == "https://example.com"

    def test_parsed_url_fallback_to_url(self) -> None:
        client = SearXNGClient()
        data = {
            "results": [
                {
                    "url": "https://example.com/page?utm_source=test",
                    "title": "Test",
                }
            ]
        }
        results = client._parse_results(data)
        # When parsed_url is not present or not a list, falls back to url
        assert results[0].parsed_url == "https://example.com/page?utm_source=test"

    def test_parsed_url_first_element(self) -> None:
        client = SearXNGClient()
        data = {
            "results": [
                {
                    "url": "https://example.com/page",
                    "parsed_url": [
                        "https://example.com/cleaned",
                        "https://example.com/page",
                    ],
                }
            ]
        }
        results = client._parse_results(data)
        assert results[0].parsed_url == "https://example.com/cleaned"
