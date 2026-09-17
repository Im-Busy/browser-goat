"""Offline regressions for pipeline wiring and installed-backend contracts."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from browser_goat.cache import TTLFetchCache
from browser_goat.extraction.scrapling_fetcher import ScraplingFetcher
from browser_goat.models import (
    ExtractedSource,
    FetchResult,
    RankedResult,
    RawSearchResult,
    SearchResult,
)
from browser_goat.router import MAX_CONCURRENT_FETCHES, BrowserGoat


def source(url: str) -> ExtractedSource:
    return ExtractedSource(
        url=url, title=url, rational="Relevant", evidence="Evidence", summary="Summary",
        extraction_tier=1, used_scrapling=False, rank=1, final_score=1, engine="google",
    )


async def test_crawl4ai_success_does_not_raise() -> None:
    fetcher = ScraplingFetcher()
    failure = FetchResult(url="https://example.com")
    with (
        patch.object(fetcher, "_try_httpx", AsyncMock(return_value=failure)),
        patch.object(fetcher, "_try_scrapling", AsyncMock(return_value=failure)),
        patch.object(fetcher, "_try_crawl4ai", AsyncMock(return_value=FetchResult(
            url=failure.url, success=True, html="<p>content</p>", status_code=200,
        ))),
    ):
        result = await fetcher.fetch(failure.url)
    assert result.used_crawl4ai and result.fetch_tier == 4


async def test_library_context_manager_closes_clients() -> None:
    goat = BrowserGoat()
    with patch.object(goat, "close", AsyncMock()) as close:
        async with goat as entered:
            assert entered is goat
        close.assert_awaited_once()


async def test_explicit_language_reaches_backend() -> None:
    goat = BrowserGoat()
    with patch.object(goat.searxng, "search", AsyncMock(return_value=[])) as search:
        await goat.search("Python", language="fr")
    assert search.call_args.kwargs["language"] == "fr"
    assert search.call_args.kwargs["lang_params"].hl == "fr"


async def test_explore_keeps_variant_results_and_constraints() -> None:
    goat = BrowserGoat()

    async def search(query: str, **kwargs: object) -> list[RawSearchResult]:
        return [RawSearchResult(url=f"https://example.com/{'variant' if 'programming' in query else 'direct'}")]

    with (
        patch.object(goat.searxng, "search", AsyncMock(side_effect=search)) as backend,
        patch.object(goat, "_extract_sources", AsyncMock(return_value=([], [], 0))) as extract,
    ):
        await goat.search("python", strategy="explore", engines=["bing"], language="fr", time_range="week")
    assert {r.url for r in extract.call_args.args[0]} == {
        "https://example.com/direct", "https://example.com/variant",
    }
    assert backend.await_count == 2  # no discarded variants and redundant third search
    assert all(c.kwargs["time_range"] == "week" for c in backend.call_args_list)


async def test_verified_search_returns_plurality_with_matching_sources() -> None:
    goat = BrowserGoat()
    loser = SearchResult(answer="loser", sources=[source("https://example.com/loser")])
    winner = SearchResult(answer="winner", sources=[source("https://example.com/winner")])
    with patch.object(goat.multi_rollout, "execute", AsyncMock(return_value=[loser, winner, winner])) as run:
        result = await goat.search("Python", reliability_mode="high", max_sources=1,
                                   engines=["bing"], language="fr", time_range="week", strategy="explore")
    assert result.answer == "winner"
    assert result.sources == winner.sources
    assert result.verification.rollout_count == 3
    assert run.call_args.kwargs["search_options"]["max_sources"] == 1


async def test_no_llm_tie_is_not_reported_as_llm_verification() -> None:
    goat = BrowserGoat()
    with patch.object(goat.multi_rollout, "execute", AsyncMock(return_value=[
        SearchResult(answer="one"), SearchResult(answer="two"),
    ])):
        result = await goat.search("Python", reliability_mode="maximum")
    assert result.verification.method == "fallback"


async def test_extraction_concurrency_is_bounded() -> None:
    goat = BrowserGoat()
    active = peak = 0

    async def fetch(url: str, **kwargs: object) -> FetchResult:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.005)
        active -= 1
        return FetchResult(url=url, status_code=200, success=True, html="<p>" + "Python documentation. " * 20 + "</p>")

    ranked = [RankedResult(url=f"https://example.com/{i}", normalized_url=f"https://example.com/{i}") for i in range(20)]
    with patch.object(goat.scrapling, "fetch", AsyncMock(side_effect=fetch)):
        sources, _, _ = await goat._extract_sources(ranked, "Python", None)
    assert len(sources) == 20
    assert peak <= MAX_CONCURRENT_FETCHES


@pytest.mark.parametrize("options", [{"max_sources": 0}, {"strategy": "typo"}, {"time_range": "decade"}])
async def test_invalid_search_options_rejected_before_io(options: dict[str, object]) -> None:
    goat = BrowserGoat()
    with patch.object(goat.searxng, "search", AsyncMock()) as search, pytest.raises(ValueError):
        await goat.search("Python", **options)
    search.assert_not_awaited()


def test_negative_cache_capacity_rejected() -> None:
    with pytest.raises(ValueError):
        TTLFetchCache(max_entries=-1)


async def test_blocked_only_search_does_not_fetch() -> None:
    goat = BrowserGoat()
    with (
        patch.object(goat.searxng, "search", AsyncMock(return_value=[RawSearchResult(
            url="https://facebook.com/python", title="Python", content="Python documentation " * 20,
        )])),
        patch.object(goat.scrapling, "fetch", AsyncMock()) as fetch,
    ):
        result = await goat.search("Python")
    assert result.sources == []
    fetch.assert_not_awaited()


async def test_duplicate_urls_do_not_consume_source_slots() -> None:
    goat = BrowserGoat()
    urls = ["https://example.com/python", "https://example.com/python?utm_source=x",
            "https://example.com/asyncio"]
    raw = [RawSearchResult(url=url, title="Python asyncio", content="Python asyncio " * 10) for url in urls]

    async def fetch(url: str, **kwargs: object) -> FetchResult:
        return FetchResult(url=url, success=True, status_code=200, html="<p>Python asyncio " + "example " * 30 + "</p>")

    with patch.object(goat.searxng, "search", AsyncMock(return_value=raw)), patch.object(goat.scrapling, "fetch", AsyncMock(side_effect=fetch)) as fetch_mock:
        result = await goat.search("Python asyncio", max_sources=2)
    assert {s.url for s in result.sources} == {urls[0], urls[2]}
    assert fetch_mock.await_count == 2
