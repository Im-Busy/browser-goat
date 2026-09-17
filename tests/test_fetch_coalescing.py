"""Deterministic cache stampede/cancellation tests, with no external I/O."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from browser_goat.models import FetchResult
from browser_goat.router import BrowserGoat

URL = "https://example.com"


@pytest.mark.parametrize("successful", [True, False])
async def test_simultaneous_misses_share_result_and_failures_can_retry(successful: bool) -> None:
    goat = BrowserGoat()
    started, release = asyncio.Event(), asyncio.Event()

    async def fetch(*args: object, **kwargs: object) -> FetchResult:
        started.set()
        await release.wait()
        return FetchResult(url=URL, status_code=200 if successful else 503,
                           success=successful, html="<p>Python</p>" if successful else "")

    with patch.object(goat.scrapling, "fetch", AsyncMock(side_effect=fetch)) as backend:
        tasks = [asyncio.create_task(goat._fetch_with_cache(URL, None)) for _ in range(8)]
        await started.wait()
        await asyncio.sleep(0)
        release.set()
        results = await asyncio.gather(*tasks)
        assert backend.await_count == 1
        assert all(r.success == successful for r in results)
        await goat._fetch_with_cache(URL, None)
        assert backend.await_count == (1 if successful else 2)
    assert not goat._inflight_fetches


async def test_cancelled_waiter_does_not_cancel_other_consumers() -> None:
    goat = BrowserGoat()
    started, release, cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def fetch(*args: object, **kwargs: object) -> FetchResult:
        started.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return FetchResult(url=URL, status_code=200, success=True, html="<p>Python</p>")

    with patch.object(goat.scrapling, "fetch", AsyncMock(side_effect=fetch)) as backend:
        first = asyncio.create_task(goat._fetch_with_cache(URL, None))
        await started.wait()
        other = asyncio.create_task(goat._fetch_with_cache(URL, None))
        await asyncio.sleep(0)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        assert not cancelled.is_set()
        release.set()
        assert (await other).success
        assert backend.await_count == 1
    assert not goat._inflight_fetches


async def test_last_waiter_cancellation_cleans_up_and_allows_retry() -> None:
    goat = BrowserGoat()
    started, cancelled = asyncio.Event(), asyncio.Event()

    async def fetch(*args: object, **kwargs: object) -> FetchResult:
        started.set()
        try:
            await asyncio.sleep(30)
        finally:
            cancelled.set()
        return FetchResult(url=URL)

    with patch.object(goat.scrapling, "fetch", AsyncMock(side_effect=fetch)) as backend:
        task = asyncio.create_task(goat._fetch_with_cache(URL, None))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cancelled.is_set()
        assert not goat._inflight_fetches
        backend.side_effect = None
        backend.return_value = FetchResult(url=URL, status_code=200, success=True, html="<p>Python</p>")
        assert (await goat._fetch_with_cache(URL, None)).success


async def test_inflight_url_count_is_bounded_and_backpressure_drains() -> None:
    goat = BrowserGoat(cache_max_entries=0)
    started, release = asyncio.Event(), asyncio.Event()

    async def fetch(url: str, **kwargs: object) -> FetchResult:
        started.set()
        await release.wait()
        return FetchResult(url=url, status_code=200, success=True, html="<p>Python</p>")

    with patch("browser_goat.router.MAX_INFLIGHT_FETCHES", 2), patch.object(goat.scrapling, "fetch", AsyncMock(side_effect=fetch)) as backend:
        tasks = [asyncio.create_task(goat._fetch_with_cache(f"{URL}/{i}", None)) for i in range(5)]
        await started.wait()
        await asyncio.sleep(0)
        assert len(goat._inflight_fetches) == 2
        release.set()
        assert all(r.success for r in await asyncio.gather(*tasks))
    assert backend.await_count == 5
    assert not goat._inflight_fetches


async def test_backend_exception_does_not_leak_inflight_entry() -> None:
    goat = BrowserGoat()
    with patch.object(goat.scrapling, "fetch", AsyncMock(side_effect=RuntimeError("failed"))) as backend:
        results = await asyncio.gather(*[goat._fetch_with_cache(URL, None) for _ in range(4)], return_exceptions=True)
        assert all(isinstance(r, RuntimeError) for r in results)
        assert backend.await_count == 1
        assert not goat._inflight_fetches
        backend.side_effect = None
        backend.return_value = FetchResult(url=URL, status_code=200, success=True, html="<p>Python</p>")
        assert (await goat._fetch_with_cache(URL, None)).success


async def test_close_drains_inflight_work() -> None:
    goat = BrowserGoat()
    started = asyncio.Event()

    async def fetch(*args: object, **kwargs: object) -> FetchResult:
        started.set()
        await asyncio.sleep(30)
        return FetchResult(url=URL)

    with patch.object(goat.scrapling, "fetch", AsyncMock(side_effect=fetch)):
        task = asyncio.create_task(goat._fetch_with_cache(URL, None))
        await started.wait()
        await goat.close()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert not goat._inflight_fetches
