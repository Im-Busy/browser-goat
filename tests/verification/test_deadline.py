"""Verification deadline regressions with local fakes, never an external LLM."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from browser_goat.models import FetchResult, RawSearchResult, SearchResult
from browser_goat.router import MAX_CONCURRENT_FETCHES, BrowserGoat
from browser_goat.verification.multi_rollout import MultiRollout


async def test_deadline_preserves_fast_rollout_and_drains_slow_browser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(MultiRollout, "COLLECTION_TIMEOUT_SECONDS", 0.1, raising=False)
    goat = BrowserGoat()
    navigation_started, navigation_cancelled = asyncio.Event(), asyncio.Event()

    async def search(query: str, **kwargs: object) -> list[RawSearchResult]:
        engines = kwargs["engines"]
        if engines == ["bing", "scholar"]:
            raise httpx.ConnectError("simulated backend failure")
        suffix = "fast" if engines == ["google", "bing"] else "slow"
        return [RawSearchResult(url=f"https://example.com/{suffix}", title="Python asyncio",
                                content="Python asyncio documentation for asynchronous tasks. " * 5)]

    async def http_fetch(url: str, *args: object) -> FetchResult:
        if url.endswith("fast"):
            return FetchResult(url=url, status_code=200, success=True,
                               html="<article>" + "Python asyncio runs concurrent tasks. " * 20 + "</article>")
        return FetchResult(url=url, error="Try browser")

    async def navigate(*args: object, **kwargs: object) -> None:
        navigation_started.set()
        try:
            await asyncio.sleep(30)
        finally:
            navigation_cancelled.set()

    page = SimpleNamespace(goto=AsyncMock(side_effect=navigate))
    browser = SimpleNamespace(new_page=AsyncMock(return_value=page), close=AsyncMock())
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=SimpleNamespace(
        chromium=SimpleNamespace(launch=AsyncMock(return_value=browser)),
    ))
    manager.__aexit__ = AsyncMock(return_value=False)
    failed = FetchResult(url="https://example.com/slow", error="Try next tier")
    with (
        patch.object(goat.searxng, "search", AsyncMock(side_effect=search)),
        patch.object(goat.scrapling, "_try_httpx", AsyncMock(side_effect=http_fetch)),
        patch.object(goat.scrapling, "_try_scrapling", AsyncMock(return_value=failed)),
        patch.object(goat.scrapling, "_try_crawl4ai", AsyncMock(return_value=failed)),
        patch("playwright.async_api.async_playwright", return_value=manager),
    ):
        result = await asyncio.wait_for(goat.verify("Python asyncio", rollouts=3), timeout=2)
    assert navigation_started.is_set() and navigation_cancelled.is_set()
    browser.close.assert_awaited_once()
    assert not goat._inflight_fetches
    assert goat._fetch_semaphore._value == MAX_CONCURRENT_FETCHES
    assert result["rollouts_run"] == 1
    assert result["sources"][0]["url"].endswith("fast")
    verification = result["verification"]
    assert verification["timed_out"] and verification["partial"]
    assert verification["failed_rollouts"] == 1
    assert verification["cancelled_rollouts"] == 1
    assert verification["requested_rollouts"] == 3
    assert verification["stop_reason"] == "deadline"
    assert verification["method"] == "fallback" and not verification["is_consensus"]
    await goat.close()


async def test_no_completions_returns_explicit_timeout_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MultiRollout, "COLLECTION_TIMEOUT_SECONDS", 0.02, raising=False)
    goat = BrowserGoat()

    async def slow(**kwargs: object) -> SearchResult:
        await asyncio.sleep(30)
        return SearchResult(answer="not reached")

    with patch.object(goat, "search", AsyncMock(side_effect=slow)):
        result = await asyncio.wait_for(goat.verify("Python", 3), timeout=1)
    assert result["rollouts_run"] == 0 and result["sources"] == []
    assert result["verification"]["method"] == "rollout_failure"
    assert result["verification"]["timed_out"] is True
    assert result["verification"]["cancelled_rollouts"] == 3
    assert result["reliability"]["quality_passed"] is False


async def test_verify_source_cap_does_not_override_search_max_sources() -> None:
    goat = BrowserGoat()
    with patch.object(goat.multi_rollout, "execute", AsyncMock(return_value=[])) as execute:
        await goat.verify("Python", 3)
        assert execute.call_args.kwargs["search_options"]["max_sources"] == 3
        await goat.search("Python", reliability_mode="high", max_sources=17)
        assert execute.call_args.kwargs["search_options"]["max_sources"] == 17


async def test_verifier_must_use_remaining_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MultiRollout, "COLLECTION_TIMEOUT_SECONDS", 0.02, raising=False)
    goat = BrowserGoat()
    cancelled = asyncio.Event()

    async def slow_verifier(**kwargs: object) -> None:
        try:
            await asyncio.sleep(30)
        finally:
            cancelled.set()

    with (
        patch.object(goat.multi_rollout, "execute", AsyncMock(return_value=[
            SearchResult(answer="one"), SearchResult(answer="two"),
        ])),
        patch.object(goat.llm_verifier, "verify", AsyncMock(side_effect=slow_verifier)),
    ):
        result = await asyncio.wait_for(goat.verify("Python", 6), timeout=1)
    assert cancelled.is_set()
    assert result["verification"]["method"] == "fallback"
    assert result["verification"]["timed_out"] is True
    assert result["verification"]["stop_reason"] == "verifier_timeout"
