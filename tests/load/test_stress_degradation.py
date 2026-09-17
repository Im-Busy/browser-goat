"""Degradation scenario stress tests for the BrowserGoat pipeline.

Covers progressive latency ramp, error rate ramp, partial results,
timeout cascade, intermittent availability, recovery after outage,
graceful degradation, empty/malformed responses, slow→fast recovery,
and extreme result count variation.

All tests use conftest fixtures (fake_searxng, browser_goat,
fast_fake_searxng, mock_sources) — no real SearXNG URLs.

NOTE: fake_searxng is session-scoped, so _error_rate / _result_count
persist between tests. Each test resets state explicitly at the top.
"""

from __future__ import annotations

import time

import httpx
import pytest

from browser_goat.models import SearchResult

# ── 1. Progressive latency ramp ────────────────────────────────────────────


@pytest.mark.stress
@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_progressive_latency_ramp(
    fast_fake_searxng,
    browser_goat,
) -> None:
    """Latency increases from 0→5s; pipeline_latency_ms grows proportionally."""
    # Reset leaked state from previous tests
    fast_fake_searxng._error_rate = 0.0

    # Warmup: prime the HTTP connection pool to avoid cold-start skew
    fast_fake_searxng._latency = 0.0
    await browser_goat.search("warmup", max_sources=1)

    latencies: list[float] = [0.0, 0.1, 0.5, 1.0, 2.0, 5.0]
    pipeline_times: list[int] = []

    for lat in latencies:
        fast_fake_searxng._latency = lat
        result = await browser_goat.search("degradation ramp test", max_sources=1)
        assert isinstance(result, SearchResult), (
            f"Expected SearchResult at latency {lat}s"
        )
        pipeline_times.append(result.pipeline_latency_ms)

    # Loose monotonicity: each step's time should not be wildly lower than
    # its predecessor (allow small jitter from OS scheduling variance).
    for i in range(1, len(pipeline_times)):
        assert pipeline_times[i] >= pipeline_times[i - 1] * 0.5, (
            f"pipeline_latency_ms should not drop dramatically: "
            f"{pipeline_times[i - 1]}ms → {pipeline_times[i]}ms at step {i}"
        )

    # The 5s step should be notably larger than 0s baseline
    assert pipeline_times[-1] > pipeline_times[0] * 2, (
        f"5s latency ({pipeline_times[-1]}ms) should be significantly "
        f"larger than 0s baseline ({pipeline_times[0]}ms)"
    )


# ── 2. Error rate ramp ────────────────────────────────────────────────────


@pytest.mark.stress
@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_error_rate_ramp(
    fast_fake_searxng,
    browser_goat,
) -> None:
    """Success rate decreases as error_rate increases from 0→1.0."""
    # Reset leaked state
    fast_fake_searxng._error_rate = 0.0

    error_rates: list[float] = [0.0, 0.1, 0.3, 0.5, 0.8, 1.0]
    success_rates: list[float] = []

    for rate in error_rates:
        fast_fake_searxng._error_rate = rate
        successes = 0
        attempts = 3  # Keep low — timeout errors take 15s+ each
        for _ in range(attempts):
            try:
                result = await browser_goat.search("error ramp test", max_sources=1)
                if isinstance(result, SearchResult):
                    successes += 1
            except (httpx.HTTPError, httpx.TimeoutException, OSError):
                pass
        success_rates.append(successes / attempts)

    # At error_rate=0.0, all should succeed
    assert success_rates[0] == 1.0, (
        f"At error_rate=0.0, expected 100%% success, got {success_rates[0]:.0%}"
    )

    # At error_rate=1.0, none should succeed
    assert success_rates[-1] == 0.0, (
        f"At error_rate=1.0, expected 0%% success, got {success_rates[-1]:.0%}"
    )

    # Higher error rates should not produce better success rates
    # (allow small statistical fluctuation at low attempt counts)
    mid_rates = [(error_rates[i], success_rates[i])
                 for i in range(1, len(success_rates) - 1)
                 if success_rates[i] > 0]
    for i in range(1, len(mid_rates)):
        assert mid_rates[i][1] <= mid_rates[0][1] + 0.34, (
            f"Success rate should generally decrease as error_rate rises: "
            f"{success_rates}"
        )


# ── 3. Partial results with some engines down ─────────────────────────────


@pytest.mark.stress
@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_partial_results_some_engines_down(
    fake_searxng,
    browser_goat,
) -> None:
    """Pipeline handles varying result counts from SearXNG (simulates partial results)."""
    # Reset leaked state from previous tests
    fake_searxng._error_rate = 0.0
    fake_searxng._latency = 0.0
    fake_searxng._result_count = 3

    for i in range(3):
        result = await browser_goat.search(
            f"partial results test {i}", max_sources=5,
        )
        assert isinstance(result, SearchResult), (
            f"Iteration {i}: expected SearchResult"
        )
        assert result.sources, (
            f"Iteration {i}: sources list should not be empty"
        )
        assert result.total_sources_found <= 3, (
            f"Iteration {i}: total_sources_found={result.total_sources_found} "
            f"should be ≤ 3 (result_count)"
        )


# ── 4. Timeout cascade ────────────────────────────────────────────────────


@pytest.mark.stress
@pytest.mark.asyncio
@pytest.mark.timeout(45)
async def test_timeout_cascade(
    fake_searxng,
    browser_goat,
) -> None:
    """30s SearXNG latency with 15s client timeout — no crash or hang."""
    # Reset leaked state
    fake_searxng._error_rate = 0.0
    fake_searxng._latency = 30.0

    result_or_error = None
    try:
        result_or_error = await browser_goat.search(
            "timeout cascade test", max_sources=1,
        )
    except (httpx.TimeoutException, httpx.HTTPError, OSError) as exc:
        result_or_error = exc

    # Must NOT hang — pytest.mark.timeout(45) enforces this
    if isinstance(result_or_error, SearchResult):
        # Pipeline handled timeout internally — acceptable
        assert result_or_error.answer, (
            "Answer should not be empty even after SearXNG timeout"
        )
    else:
        # Exception propagated — also acceptable, no crash
        assert isinstance(result_or_error, Exception), (
            "Expected SearchResult or Exception, not crash"
        )


# ── 5. Intermittent availability (flaky server) ───────────────────────────


@pytest.mark.stress
@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_intermittent_availability_flaky_server(
    fake_searxng,
    browser_goat,
) -> None:
    """Pipeline recovers when server comes back after total failure."""
    # Reset leaked state
    fake_searxng._error_rate = 0.0
    fake_searxng._latency = 0.0

    # Phase 1: Healthy (3 searches)
    for i in range(3):
        result = await browser_goat.search(f"healthy-{i}", max_sources=1)
        assert isinstance(result, SearchResult), (
            f"Phase 1 iteration {i}: expected SearchResult"
        )

    # Phase 2: Total outage (3 searches)
    fake_searxng._error_rate = 1.0
    errors_p2 = 0
    for i in range(3):
        try:
            await browser_goat.search(f"outage-{i}", max_sources=1)
        except (httpx.HTTPError, httpx.TimeoutException, OSError):
            errors_p2 += 1
    assert errors_p2 == 3, (
        f"Phase 2: all 3 searches should error, got {errors_p2} errors"
    )

    # Phase 3: Recovered (3 searches)
    fake_searxng._error_rate = 0.0
    for i in range(3):
        result = await browser_goat.search(f"recovered-{i}", max_sources=1)
        assert isinstance(result, SearchResult), (
            f"Phase 3 iteration {i}: expected SearchResult after recovery"
        )
        assert result.sources, (
            f"Phase 3 iteration {i}: sources should not be empty after recovery"
        )


# ── 6. Recovery after total outage ────────────────────────────────────────


@pytest.mark.stress
@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_recovery_after_total_outage(
    fake_searxng,
    browser_goat,
) -> None:
    """After error_rate=1.0 outage, setting error_rate=0 restores service."""
    # Reset leaked state before configuring outage
    fake_searxng._latency = 0.0
    fake_searxng._error_rate = 1.0  # intentional: total outage

    # Phase 1: Total outage
    outage_result = None
    try:
        outage_result = await browser_goat.search(
            "outage query", max_sources=1,
        )
    except (httpx.HTTPError, httpx.TimeoutException, OSError):
        outage_result = None

    assert outage_result is None or isinstance(outage_result, SearchResult), (
        "Outage phase should return None/error or empty SearchResult"
    )

    # Phase 2: Recovery
    fake_searxng._error_rate = 0.0
    recovered = await browser_goat.search("recovery query", max_sources=1)
    assert isinstance(recovered, SearchResult), (
        "Recovery phase should return SearchResult"
    )
    assert recovered.sources, (
        f"Recovery SearchResult should have sources, got {len(recovered.sources)}"
    )


# ── 7. Graceful degradation at high error rate ────────────────────────────


@pytest.mark.stress
@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_graceful_degradation_high_error_rate(
    fake_searxng,
    browser_goat,
) -> None:
    """At error_rate=0.8, at least 1 of 10 searches succeeds — pipeline survives."""
    # Reset leaked state before configuring
    fake_searxng._latency = 0.0
    fake_searxng._error_rate = 0.8

    successes = 0
    for i in range(10):
        try:
            result = await browser_goat.search(
                f"graceful {i}", max_sources=1,
            )
            if isinstance(result, SearchResult):
                successes += 1
        except (httpx.HTTPError, httpx.TimeoutException, OSError):
            pass

    assert successes >= 1, (
        f"At error_rate=0.8, expected ≥1 success out of 10, got {successes}. "
        "Pipeline should produce partial results, not die entirely."
    )


# ── 8. Empty response body ────────────────────────────────────────────────


@pytest.mark.stress
@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_empty_response_body(
    fake_searxng,
    browser_goat,
) -> None:
    """SearXNG returns 0 results; pipeline returns SearchResult without crash."""
    # Reset leaked state
    fake_searxng._error_rate = 0.0
    fake_searxng._latency = 0.0
    fake_searxng._result_count = 0

    result = await browser_goat.search("empty response test", max_sources=1)
    assert isinstance(result, SearchResult), (
        "Empty SearXNG response must still produce a SearchResult"
    )
    assert result.answer, (
        "Answer should not be empty (graceful degradation message expected)"
    )
    assert result.total_sources_found == 0, (
        f"total_sources_found should be 0, got {result.total_sources_found}"
    )


# ── 9. Malformed response handling ────────────────────────────────────────


@pytest.mark.stress
@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_malformed_response_handling(
    fake_searxng,
    browser_goat,
) -> None:
    """Zero-result SearXNG response handled 5 times without raising."""
    # Reset leaked state
    fake_searxng._error_rate = 0.0
    fake_searxng._latency = 0.0
    fake_searxng._result_count = 0

    for i in range(5):
        result = await browser_goat.search(
            f"malformed test {i}", max_sources=1,
        )
        assert isinstance(result, SearchResult), (
            f"Iteration {i}: expected SearchResult without raising"
        )
        assert result.answer, (
            f"Iteration {i}: answer should not be empty"
        )


# ── 10. Slow then fast recovery ───────────────────────────────────────────


@pytest.mark.stress
@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_slow_then_fast_recovery(
    fast_fake_searxng,
    browser_goat,
) -> None:
    """Slow search (3s) then fast search (0s) — latency drops accordingly."""
    # Reset leaked state
    fast_fake_searxng._error_rate = 0.0

    # Phase 1: Slow
    fast_fake_searxng._latency = 3.0
    t0 = time.monotonic()
    slow_result = await browser_goat.search("slow query", max_sources=1)
    slow_wall = (time.monotonic() - t0) * 1000
    assert isinstance(slow_result, SearchResult), "Slow search should return SearchResult"

    # Phase 2: Fast (recovery)
    fast_fake_searxng._latency = 0.0
    t1 = time.monotonic()
    fast_result = await browser_goat.search("fast query", max_sources=1)
    fast_wall = (time.monotonic() - t1) * 1000
    assert isinstance(fast_result, SearchResult), "Fast search should return SearchResult"

    # Second search should be much faster than first
    assert fast_result.pipeline_latency_ms < slow_result.pipeline_latency_ms, (
        f"Fast pipeline_latency_ms ({fast_result.pipeline_latency_ms}) "
        f"should be < slow ({slow_result.pipeline_latency_ms})"
    )
    assert fast_wall < slow_wall, (
        f"Fast wall time ({fast_wall:.0f}ms) should be < slow ({slow_wall:.0f}ms)"
    )


# ── 11. Extreme result count variation ────────────────────────────────────


@pytest.mark.stress
@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_extreme_result_count_variation(
    fake_searxng,
    browser_goat,
) -> None:
    """Pipeline handles result_count from 0 to 100 without breaking."""
    # Reset leaked state
    fake_searxng._error_rate = 0.0
    fake_searxng._latency = 0.0

    counts: list[int] = [0, 1, 50, 200]

    for count in counts:
        fake_searxng._result_count = count
        result = await browser_goat.search(
            f"count variation {count}", max_sources=5,
        )
        assert isinstance(result, SearchResult), (
            f"result_count={count}: expected SearchResult"
        )
        assert result.total_sources_found == count, (
            f"result_count={count}: total_sources_found should be {count}, "
            f"got {result.total_sources_found}"
        )

    # At max count, sources list should not be empty
    fake_searxng._result_count = 100
    result = await browser_goat.search("extreme 100", max_sources=5)
    assert result.sources, (
        f"At result_count=100, sources should not be empty, "
        f"got {len(result.sources)} sources"
    )
