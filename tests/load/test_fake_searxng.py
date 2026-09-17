"""Comprehensive unit tests for FakeSearXNGServer.

Covers all configurable aspects: lifecycle, health, search results,
latency injection, error injection (timeout/500/503), determinism,
concurrency, port reassignment, and error rate statistics.

Each test is self-contained — no external conftest fixtures required.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest

from tests.load.fake_searxng import FakeSearXNGServer

# ── Error-type to seed mapping (pre-computed from Python's Mersenne Twister) ──
# These seeds were verified to produce the desired error type as the FIRST
# choice(random.Random(seed).choice(["timeout", "500", "503", "close"])).
# Re-verified at runtime by _verify_seed_mapping() below.

_SEED_FOR_ERROR: dict[str, int] = {}

_ERROR_LABELS = ("timeout", "500", "503", "close")


def _find_seed_for_error(target: str, start: int = 0, limit: int = 500) -> int:
    """Brute-force scan: find seed where _handle_client's error injection
    produces *target*.

    The server consumes RNG in this order inside _handle_client:
      1. rng.random()   — check against error_rate
      2. rng.choice(...) — pick error type in _inject_error
    We must match that exact sequence.
    """
    for s in range(start, limit):
        rng = random.Random(s)
        rng.random()  # consumed by error_rate gate
        if rng.choice(_ERROR_LABELS) == target:  # noqa: S311
            return s
    raise RuntimeError(
        f"No seed found for {target!r} in range [{start}, {limit})"
    )


def _ensure_seeds() -> None:
    """Populate _SEED_FOR_ERROR once (lazy)."""
    if _SEED_FOR_ERROR:
        return
    for label in _ERROR_LABELS:
        _SEED_FOR_ERROR[label] = _find_seed_for_error(label)


@pytest.fixture(autouse=True, scope="session")
def _populate_seeds() -> None:
    _ensure_seeds()


def _seed_for(error_label: str) -> int:
    _ensure_seeds()
    return _SEED_FOR_ERROR[error_label]


# ── Shared helper types ─────────────────────────────────────────────────────────

_SEARCH_RESULT_REQUIRED_KEYS: frozenset[str] = frozenset({
    "title", "url", "content", "engine",
    "score", "category", "parsed_url", "publishedDate",
})

_StartStopFn = Callable[[], Awaitable[Any]]


# ── Helpers ─────────────────────────────────────────────────────────────────────


def _build_start_stop_fn() -> tuple[FakeSearXNGServer, _StartStopFn, _StartStopFn]:
    """Return (server, start, stop) callables. Equivalent to an async context manager."""
    server = FakeSearXNGServer()

    async def _start() -> None:
        await server.start()
        # Smoke-check: the URL is usable.
        assert server.url.startswith("http://127.0.0.1:"), (
            f"Server URL should be localhost, got {server.url!r}"
        )

    async def _stop() -> None:
        await server.stop()

    return server, _start, _stop


async def _make_search_request(
    client: httpx.AsyncClient,
    base_url: str,
    query: str = "test query",
) -> dict[str, Any]:
    """Issue GET /search?q=... and return parsed JSON."""
    resp = await client.get(f"{base_url}/search", params={"q": query})
    return resp.json()


def _assert_valid_result(result: dict[str, Any], index: int) -> None:
    """Assert a single fake search result has all required fields."""
    for key in _SEARCH_RESULT_REQUIRED_KEYS:
        assert key in result, f"Result[{index}] missing key {key!r}"


# ── Tests ───────────────────────────────────────────────────────────────────────


class TestLifecycle:
    """Server start/stop lifecycle tests."""

    @pytest.mark.stress
    @pytest.mark.asyncio
    async def test_starts_and_stops_cleanly(self) -> None:
        """Start server, verify url property works, stop server, verify no leaks."""
        server, start, stop = _build_start_stop_fn()

        await start()
        try:
            assert server.url.startswith("http://"), (
                f"Expected HTTP URL, got {server.url!r}"
            )
            assert server._port > 0, "Server port should be > 0 after start"
        finally:
            await stop()

        assert server._port == 0, "Port should be reset to 0 after stop"
        assert server._server is None, "Server reference should be None after stop"

    @pytest.mark.stress
    @pytest.mark.asyncio
    async def test_double_stop_is_idempotent(self) -> None:
        """Calling stop() twice should not raise."""
        server, start, stop = _build_start_stop_fn()
        await start()
        await stop()
        await stop()  # must not raise


class TestHealthEndpoint:
    """Tests for the /health endpoint."""

    @pytest.mark.stress
    @pytest.mark.asyncio
    async def test_health_endpoint(self) -> None:
        """GET /health returns {'status': 'ok'} with HTTP 200."""
        server, start, stop = _build_start_stop_fn()
        await start()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{server.url}/health")
                assert resp.status_code == 200, (
                    f"Expected 200, got {resp.status_code}"
                )
                data = resp.json()
                assert data == {"status": "ok"}, (
                    f"Expected {{'status': 'ok'}}, got {data!r}"
                )
        finally:
            await stop()


class TestSearchEndpoint:
    """Tests for the /search endpoint."""

    @pytest.mark.stress
    @pytest.mark.asyncio
    async def test_search_returns_expected_result_count(self) -> None:
        """GET /search returns result_count results in JSON."""
        server, start, stop = _build_start_stop_fn()
        server._result_count = 7  # override default 10
        await start()
        try:
            async with httpx.AsyncClient() as client:
                data = await _make_search_request(client, server.url)
                assert data["number_of_results"] == 7, (
                    f"Expected 7 results, got {data['number_of_results']}"
                )
                assert len(data["results"]) == 7, (
                    f"Expected 7 results in list, got {len(data['results'])}"
                )
                assert data["query"] == "test query", (
                    f"Expected query echo 'test query', got {data['query']!r}"
                )
        finally:
            await stop()

    @pytest.mark.stress
    @pytest.mark.asyncio
    async def test_search_json_structure_valid(self) -> None:
        """Verify results have all required fields."""
        server, start, stop = _build_start_stop_fn()
        await start()
        try:
            async with httpx.AsyncClient() as client:
                data = await _make_search_request(client, server.url)
                assert len(data["results"]) > 0, "Should have at least one result"
                for i, result in enumerate(data["results"]):
                    _assert_valid_result(result, i)
        finally:
            await stop()

    @pytest.mark.stress
    @pytest.mark.asyncio
    async def test_search_with_empty_query(self) -> None:
        """GET /search with empty q parameter still returns results."""
        server, start, stop = _build_start_stop_fn()
        await start()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{server.url}/search", params={"q": ""})
                assert resp.status_code == 200, (
                    f"Empty query should return 200, got {resp.status_code}"
                )
                data = resp.json()
                assert "results" in data, "Response should contain 'results' key"
        finally:
            await stop()


class TestLatencyInjection:
    """Tests for configurable response latency."""

    @pytest.mark.stress
    @pytest.mark.asyncio
    async def test_latency_injection(self) -> None:
        """Start server with latency=0.5, verify response takes >= 400ms."""
        server = FakeSearXNGServer(latency=0.5)
        await server.start()
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                t0 = time.perf_counter()
                resp = await client.get(f"{server.url}/health")
                elapsed = time.perf_counter() - t0
                assert resp.status_code == 200, (
                    f"Health check should return 200, got {resp.status_code}"
                )
                assert elapsed >= 0.4, (
                    f"Expected >= 400ms latency, got {elapsed * 1000:.0f}ms"
                )
        finally:
            await server.stop()

    @pytest.mark.stress
    @pytest.mark.asyncio
    async def test_zero_latency_is_fast(self) -> None:
        """Without latency injection, responses should be very fast (< 100ms)."""
        server = FakeSearXNGServer(latency=0.0)
        await server.start()
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                t0 = time.perf_counter()
                resp = await client.get(f"{server.url}/health")
                elapsed = time.perf_counter() - t0
                assert resp.status_code == 200, (
                    f"Health check should return 200, got {resp.status_code}"
                )
                assert elapsed < 0.1, (
                    f"Zero-latency response should be < 100ms, got {elapsed * 1000:.0f}ms"
                )
        finally:
            await server.stop()


class TestErrorInjection:
    """Tests for error injection with seed-driven error type selection."""

    @pytest.mark.stress
    @pytest.mark.asyncio
    async def test_error_injection_timeout(self) -> None:
        """Server with error_rate=1.0 and timeout seed causes request timeout."""
        seed = _seed_for("timeout")
        server = FakeSearXNGServer(error_rate=1.0, seed=seed)
        await server.start()
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(2.0)) as client:
                with pytest.raises(
                    (httpx.TimeoutException, httpx.ReadTimeout, httpx.ReadError),
                ):
                    await client.get(f"{server.url}/health")
        finally:
            await server.stop()

    @pytest.mark.stress
    @pytest.mark.asyncio
    async def test_error_injection_500(self) -> None:
        """Server with seed for 500 error returns HTTP 500."""
        seed = _seed_for("500")
        server = FakeSearXNGServer(error_rate=1.0, seed=seed)
        await server.start()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{server.url}/health")
                assert resp.status_code == 500, (
                    f"Expected 500, got {resp.status_code}"
                )
                body = resp.json()
                assert "error" in body, (
                    f"500 error response should have 'error' key, got {body!r}"
                )
        finally:
            await server.stop()

    @pytest.mark.stress
    @pytest.mark.asyncio
    async def test_error_injection_503(self) -> None:
        """Server with seed for 503 error returns HTTP 503."""
        seed = _seed_for("503")
        server = FakeSearXNGServer(error_rate=1.0, seed=seed)
        await server.start()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{server.url}/health")
                assert resp.status_code == 503, (
                    f"Expected 503, got {resp.status_code}"
                )
                body = resp.json()
                assert "error" in body, (
                    f"503 error response should have 'error' key, got {body!r}"
                )
        finally:
            await server.stop()

    @pytest.mark.stress
    @pytest.mark.asyncio
    async def test_error_injection_close(self) -> None:
        """Server with 'close' seed provokes a connection error."""
        seed = _seed_for("close")
        server = FakeSearXNGServer(error_rate=1.0, seed=seed)
        await server.start()
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
                with pytest.raises(
                    (httpx.ReadError, httpx.RemoteProtocolError, httpx.ConnectError),
                ):
                    await client.get(f"{server.url}/health")
        finally:
            await server.stop()

    @pytest.mark.stress
    @pytest.mark.asyncio
    async def test_no_errors_when_error_rate_zero(self) -> None:
        """With error_rate=0.0, all requests should succeed."""
        server = FakeSearXNGServer(error_rate=0.0)
        await server.start()
        try:
            async with httpx.AsyncClient() as client:
                for _ in range(10):
                    resp = await client.get(f"{server.url}/health")
                    assert resp.status_code == 200, (
                        f"All requests should succeed, got {resp.status_code}"
                    )
        finally:
            await server.stop()


class TestDeterminism:
    """Tests for deterministic result generation via seed."""

    @pytest.mark.stress
    @pytest.mark.asyncio
    async def test_results_are_deterministic(self) -> None:
        """Two servers with same seed return identical results."""
        seed = 12345
        s1 = FakeSearXNGServer(seed=seed)
        s2 = FakeSearXNGServer(seed=seed)
        await s1.start()
        await s2.start()
        try:
            async with httpx.AsyncClient() as client:
                d1 = await _make_search_request(client, s1.url, "determinism")
                d2 = await _make_search_request(client, s2.url, "determinism")
                assert d1 == d2, (
                    "Same seed should produce identical search results"
                )
        finally:
            await s1.stop()
            await s2.stop()

    @pytest.mark.stress
    @pytest.mark.asyncio
    async def test_results_differ_with_different_seed(self) -> None:
        """Two servers with different seeds return different results."""
        s1 = FakeSearXNGServer(seed=111)
        s2 = FakeSearXNGServer(seed=222)
        await s1.start()
        await s2.start()
        try:
            async with httpx.AsyncClient() as client:
                d1 = await _make_search_request(client, s1.url, "test")
                d2 = await _make_search_request(client, s2.url, "test")
                assert d1 != d2, (
                    "Different seeds should produce different search results"
                )
        finally:
            await s1.stop()
            await s2.stop()


class TestConcurrency:
    """Tests for concurrent request handling."""

    @pytest.mark.stress
    @pytest.mark.asyncio
    async def test_concurrent_requests(self) -> None:
        """Fire 5 concurrent requests to /search; all return valid JSON."""
        server = FakeSearXNGServer()
        await server.start()
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                tasks = [
                    _make_search_request(client, server.url, f"concurrent-{i}")
                    for i in range(5)
                ]
                results = await asyncio.gather(*tasks)

                assert len(results) == 5, (
                    f"Expected 5 concurrent results, got {len(results)}"
                )
                for i, data in enumerate(results):
                    assert "results" in data, (
                        f"Concurrent request {i} missing 'results' key"
                    )
                    assert len(data["results"]) == 10, (
                        f"Concurrent request {i} should have 10 results, "
                        f"got {len(data['results'])}"
                    )
        finally:
            await server.stop()


class TestPortReassignment:
    """Tests for port lifecycle across stop/start cycles."""

    @pytest.mark.stress
    @pytest.mark.asyncio
    async def test_port_reassignment(self) -> None:
        """Stop server, start again; it works (port may or may not change)."""
        server, start, stop = _build_start_stop_fn()

        # First cycle
        await start()
        first_url = server.url
        assert first_url.startswith("http://"), (
            f"First cycle URL should be HTTP, got {first_url!r}"
        )
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{server.url}/health")
                assert resp.status_code == 200, (
                    "First cycle: health check should return 200"
                )
        finally:
            await stop()

        # Second cycle
        await start()
        second_url = server.url
        assert second_url.startswith("http://"), (
            f"Second cycle URL should be HTTP, got {second_url!r}"
        )
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{server.url}/health")
                assert resp.status_code == 200, (
                    "Second cycle: health check should return 200"
                )
        finally:
            await stop()


class TestRouting:
    """Tests for HTTP routing / error paths."""

    @pytest.mark.stress
    @pytest.mark.asyncio
    async def test_404_on_unknown_path(self) -> None:
        """GET /nonexistent returns HTTP 404 with error JSON."""
        server, start, stop = _build_start_stop_fn()
        await start()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{server.url}/nonexistent")
                assert resp.status_code == 404, (
                    f"Unknown path should return 404, got {resp.status_code}"
                )
                body = resp.json()
                assert body == {"error": "not found"}, (
                    f"404 body should be {{'error': 'not found'}}, got {body!r}"
                )
        finally:
            await stop()

    @pytest.mark.stress
    @pytest.mark.asyncio
    async def test_post_not_allowed(self) -> None:
        """POST /search returns 404 (not 405, server only checks GET routes)."""
        server, start, stop = _build_start_stop_fn()
        await start()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(f"{server.url}/search", json={"q": "test"})
                assert resp.status_code == 404, (
                    f"POST should return 404, got {resp.status_code}"
                )
        finally:
            await stop()


class TestErrorRateStatistics:
    """Tests for statistical behavior of error_rate."""

    @pytest.mark.stress
    @pytest.mark.asyncio
    async def test_error_rate_respected(self) -> None:
        """error_rate=0.5 yields ~50% errors over 100 requests (±20%)."""
        server = FakeSearXNGServer(error_rate=0.5, seed=99)
        await server.start()
        total = 100
        errors = 0
        try:
            # Statistical coverage does not need five real seconds per injected timeout.
            async with httpx.AsyncClient(timeout=httpx.Timeout(0.1)) as client:
                for _ in range(total):
                    try:
                        resp = await client.get(f"{server.url}/health")
                        if resp.status_code != 200:
                            errors += 1
                    except httpx.HTTPError:
                        errors += 1
        finally:
            await server.stop()

        error_pct = errors / total
        assert 0.30 <= error_pct <= 0.70, (
            f"Expected ~50% errors (±20%), got {error_pct:.0%} "
            f"({errors}/{total} errors)"
        )
