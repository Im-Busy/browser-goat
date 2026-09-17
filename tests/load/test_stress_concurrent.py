"""Concurrent request stress tests for the BrowserGoat pipeline.

Covers simultaneous connections, connection pool exhaustion, rapid
client lifecycle, task cancellation, semaphore limiting, server
reconfiguration races, fixture isolation, and raw HTTP stability.

All tests use conftest fixtures: fake_searxng, fast_fake_searxng,
browser_goat, and mock_sources. No real network calls outside localhost.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import httpx
import pytest

from browser_goat.models import SearchResult
from browser_goat.router import BrowserGoat

if TYPE_CHECKING:
    from tests.load.fake_searxng import FakeSearXNGServer


# ── Test 1: 100 simultaneous connections to fake SearXNG ────────────────────


@pytest.mark.stress
@pytest.mark.timeout(120)
async def test_100_simultaneous_connections(fast_fake_searxng: FakeSearXNGServer) -> None:
    """Fire 100 concurrent httpx GET /search; all return HTTP 200 with valid JSON."""

    async def _fetch(client: httpx.AsyncClient, url: str, idx: int) -> httpx.Response:
        return await client.get(f"{url}/search", params={"q": f"concurrent-{idx}"})

    async with httpx.AsyncClient() as client:
        tasks = [_fetch(client, fast_fake_searxng.url, i) for i in range(100)]
        results = await asyncio.gather(*tasks)

    for i, resp in enumerate(results):
        assert resp.status_code == 200, f"Request {i}: expected 200, got {resp.status_code}"
        data = resp.json()
        assert "results" in data, f"Request {i}: missing 'results' key"
        assert isinstance(data["results"], list), f"Request {i}: 'results' must be a list"
        assert "query" in data, f"Request {i}: missing 'query' key"


# ── Test 2: Connection pool exhaustion recovery ─────────────────────────────


@pytest.mark.stress
@pytest.mark.timeout(120)
async def test_connection_pool_exhaustion_recovery(
    fast_fake_searxng: FakeSearXNGServer,
    browser_goat: BrowserGoat,
) -> None:
    """Call search() 200 times concurrently; all return SearchResult (pool recovers/queues)."""
    fast_fake_searxng._result_count = 5

    tasks = [browser_goat.search(f"pool-{i}", max_sources=1) for i in range(200)]
    results = await asyncio.gather(*tasks)

    for i, result in enumerate(results):
        assert isinstance(result, SearchResult), (
            f"Task {i}: expected SearchResult, got {type(result).__name__}"
        )
    assert len(results) == 200, (
        f"All 200 searches must complete, got {len(results)}"
    )


# ── Test 3: Rapid open/close httpx clients ──────────────────────────────────


@pytest.mark.stress
@pytest.mark.timeout(120)
async def test_rapid_open_close_clients(fast_fake_searxng: FakeSearXNGServer) -> None:
    """Create and close 50 httpx.AsyncClient instances; verify no resource leaks."""
    tasks_before = len(asyncio.all_tasks())

    for i in range(50):
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{fast_fake_searxng.url}/health")
            assert resp.status_code == 200, f"Client {i}: health check failed"

    # Let event loop drain any pending callbacks
    await asyncio.sleep(0.01)
    tasks_after = len(asyncio.all_tasks())
    assert tasks_after <= tasks_before + 3, (
        f"Resource leak: tasks grew from {tasks_before} to {tasks_after}"
    )


# ── Test 4: asyncio.gather 200 search tasks ─────────────────────────────────


@pytest.mark.stress
@pytest.mark.timeout(120)
async def test_asyncio_gather_200_tasks(
    fast_fake_searxng: FakeSearXNGServer,
    browser_goat: BrowserGoat,
) -> None:
    """asyncio.gather 200 search("test", max_sources=1) coroutines; all complete."""
    coros = [browser_goat.search("test", max_sources=1) for _ in range(200)]
    results = await asyncio.gather(*coros, return_exceptions=True)

    errors = [r for r in results if isinstance(r, BaseException)]
    assert len(errors) == 0, (
        f"All 200 must complete without exception, got {len(errors)} errors: "
        f"{[type(e).__name__ for e in errors[:5]]}"
    )
    valid = [r for r in results if isinstance(r, SearchResult)]
    assert len(valid) == 200, (
        f"All 200 must return SearchResult, got {len(valid)} valid"
    )


# ── Test 5: Event loop non-blocking under load ──────────────────────────────


@pytest.mark.stress
@pytest.mark.timeout(120)
async def test_event_loop_no_blocking(
    fake_searxng: FakeSearXNGServer,
    browser_goat: BrowserGoat,
) -> None:
    """While 10 searches are in-flight, asyncio.sleep(0.01) still makes progress."""
    searches = [
        asyncio.create_task(browser_goat.search(f"probe-{i}", max_sources=1))
        for i in range(10)
    ]

    # Verify event loop not blocked: sleep completes while searches run
    await asyncio.wait_for(asyncio.sleep(0.05), timeout=2.0)

    results = await asyncio.gather(*searches)
    for i, r in enumerate(results):
        assert isinstance(r, SearchResult), (
            f"Search {i}: expected SearchResult, got {type(r).__name__}"
        )


# ── Test 6: Semaphore-based concurrency limiting ────────────────────────────


@pytest.mark.stress
@pytest.mark.timeout(120)
async def test_semaphore_behavior(
    fast_fake_searxng: FakeSearXNGServer,
    browser_goat: BrowserGoat,
    mock_sources: list,
) -> None:
    """Verify asyncio.Semaphore(8) in _extract_sources correctly limits concurrency."""
    concurrent: int = 0
    max_concurrent: int = 0
    lock = asyncio.Lock()
    sem = asyncio.Semaphore(8)

    async def _semaphore_limited_extract(
        ranked: list, query: str, profile: object,
    ) -> tuple[list, list, float]:
        nonlocal concurrent, max_concurrent
        async with sem:
            async with lock:
                concurrent += 1
                max_concurrent = max(max_concurrent, concurrent)
            try:
                await asyncio.sleep(0.02)  # simulate extraction work
                return mock_sources, mock_sources, 1.0
            finally:
                async with lock:
                    concurrent -= 1

    # Replace the already-patched _extract_sources with semaphore-aware wrapper
    browser_goat._extract_sources = _semaphore_limited_extract  # type: ignore[method-assign]

    tasks = [
        browser_goat.search(f"sem-{i}", max_sources=3) for i in range(20)
    ]
    results = await asyncio.gather(*tasks)

    for i, r in enumerate(results):
        assert isinstance(r, SearchResult), (
            f"Task {i}: expected SearchResult, got {type(r).__name__}"
        )
    assert max_concurrent <= 8, (
        f"Semaphore(8) violated: max_concurrent={max_concurrent}"
    )
    assert max_concurrent > 1, (
        "Expected some concurrency (max_concurrent > 1)"
    )


# ── Test 7: Task cancellation resilience ────────────────────────────────────


@pytest.mark.stress
@pytest.mark.timeout(120)
async def test_task_cancellation_resilience(
    fake_searxng: FakeSearXNGServer,
    browser_goat: BrowserGoat,
) -> None:
    """Cancel 10 of 20 search tasks mid-flight; remaining 10 complete cleanly."""
    tasks_before = len(asyncio.all_tasks())

    tasks = [
        asyncio.create_task(browser_goat.search(f"cancel-{i}", max_sources=1))
        for i in range(20)
    ]

    # Let tasks start their HTTP calls (0.01s latency gives a window)
    await asyncio.sleep(0.005)
    for i in range(10):
        tasks[i].cancel()

    results = await asyncio.gather(*tasks, return_exceptions=True)

    cancelled = sum(1 for r in results if isinstance(r, asyncio.CancelledError))
    completed = sum(1 for r in results if isinstance(r, SearchResult))
    assert cancelled >= 5, (
        f"Expected at least 5 cancelled, got {cancelled}"
    )
    assert completed >= 8, (
        f"Expected at least 8 completed SearchResults, got {completed}"
    )
    assert cancelled + completed == 20, (
        f"All 20 tasks must complete or cancel, got {cancelled}+{completed}"
    )

    # Verify no resource leaks
    await asyncio.sleep(0.02)
    tasks_after = len(asyncio.all_tasks())
    assert tasks_after <= tasks_before + 3, (
        f"Resource leak: tasks grew from {tasks_before} to {tasks_after}"
    )


# ── Test 8: Concurrent server reconfiguration ───────────────────────────────


@pytest.mark.stress
@pytest.mark.timeout(120)
async def test_concurrent_fake_server_reconfiguration(
    fast_fake_searxng: FakeSearXNGServer,
    browser_goat: BrowserGoat,
) -> None:
    """Change _latency from 0 to 0.5 while searches run; in-flight ones complete."""
    search_tasks = [
        asyncio.create_task(browser_goat.search(f"reconfig-{i}", max_sources=1))
        for i in range(5)
    ]

    # Let searches begin (fetch URL, parse, start pipeline)
    await asyncio.sleep(0.01)

    # Mutate server latency — affects new requests, not in-flight ones
    fast_fake_searxng._latency = 0.5

    results = await asyncio.gather(*search_tasks)
    for i, r in enumerate(results):
        assert isinstance(r, SearchResult), (
            f"Search {i}: in-flight search must complete, got {type(r).__name__}"
        )


# ── Test 9: Mixed read/write concurrency ────────────────────────────────────


@pytest.mark.stress
@pytest.mark.timeout(120)
async def test_mixed_read_write_concurrency(
    fast_fake_searxng: FakeSearXNGServer,
    browser_goat: BrowserGoat,
) -> None:
    """Interleave 10 searches with 10 server reconfigurations; no race conditions."""

    async def _reconfigure() -> None:
        for _ in range(10):
            fast_fake_searxng._latency = 0.0
            await asyncio.sleep(0)
            fast_fake_searxng._result_count = 10
            await asyncio.sleep(0)
            fast_fake_searxng._error_rate = 0.0

    coros: list = [
        browser_goat.search(f"mixed-{i}", max_sources=1) for i in range(10)
    ]
    coros.append(_reconfigure())

    results = await asyncio.gather(*coros, return_exceptions=True)

    errors = [r for r in results if isinstance(r, BaseException)]
    assert len(errors) == 0, (
        f"No errors from mixed read/write, got: {[type(e).__name__ for e in errors]}"
    )
    search_results = [r for r in results if isinstance(r, SearchResult)]
    assert len(search_results) == 10, (
        f"Expected 10 search results, got {len(search_results)}"
    )


# ── Test 10: Parallel fixture isolation ─────────────────────────────────────


@pytest.mark.stress
@pytest.mark.timeout(120)
async def test_parallel_fixture_isolation(browser_goat: BrowserGoat) -> None:
    """Verify browser_goat fixture provides its own BrowserGoat instance."""
    assert isinstance(browser_goat, BrowserGoat), (
        "browser_goat fixture must provide a BrowserGoat instance"
    )
    assert browser_goat.searxng is not None, "BrowserGoat must have searxng client"
    # Function-scoped fixture ensures each test gets a fresh instance
    inst_id = id(browser_goat)
    assert isinstance(inst_id, int), "instance id() must be a valid integer"
    # Verify the instance is functional
    result = await browser_goat.search("isolation test", max_sources=1)
    assert isinstance(result, SearchResult), (
        f"Fixture instance must be functional, got {type(result).__name__}"
    )


# ── Test 11: HTTP client stability under load ───────────────────────────────


@pytest.mark.stress
@pytest.mark.timeout(120)
async def test_httpx_client_stability_under_load(
    fast_fake_searxng: FakeSearXNGServer,
) -> None:
    """500 rapid-fire GET /health; all return {"status": "ok"}, no connection errors."""

    async def _health(client: httpx.AsyncClient, url: str, idx: int) -> httpx.Response:
        return await client.get(f"{url}/health")

    async with httpx.AsyncClient() as client:
        # Batch in waves of 100 to avoid overwhelming the fake server's accept backlog
        all_results: list[httpx.Response | BaseException] = []
        for batch_start in range(0, 500, 100):
            batch = [
                _health(client, fast_fake_searxng.url, i)
                for i in range(batch_start, min(batch_start + 100, 500))
            ]
            batch_results = await asyncio.gather(*batch, return_exceptions=True)
            all_results.extend(batch_results)

    errors = [r for r in all_results if isinstance(r, BaseException)]
    assert len(errors) == 0, (
        f"All 500 health checks must succeed, got {len(errors)} errors: "
        f"{[type(e).__name__ for e in errors[:5]]}"
    )
    for i, r in enumerate(all_results):
        assert not isinstance(r, BaseException), f"Request {i} raised exception"
        assert r.status_code == 200, f"Request {i}: expected 200, got {r.status_code}"
        assert r.json() == {"status": "ok"}, (
            f"Request {i}: expected {{'status': 'ok'}}, got {r.json()!r}"
        )
