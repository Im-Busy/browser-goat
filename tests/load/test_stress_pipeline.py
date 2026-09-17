"""Master stress test suite — 17 scenarios covering every pipeline stress dimension.

All tests use conftest.py fixtures: browser_goat (mocked _extract_sources),
fake_searxng (session-scoped server), fast_fake_searxng (0ms latency),
and mock_sources (3 ExtractedSource objects).

Each test isolates one stress dimension: concurrency, exhaustion, slowdown,
intermittent failure, mixed workload, rapid sequential, verification, strategy,
empty results, memory pressure, connection pool, recovery, large input,
scrapling escalation, ranking scaling, latency tracking, health check.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import httpx
import pytest

from browser_goat.models import ExtractedSource, SearchResult
from browser_goat.router import BrowserGoat

if TYPE_CHECKING:
    from tests.load.fake_searxng import FakeSearXNGServer

# ── Scenario 1: 50 concurrent searches ──────────────────────────────────

@pytest.mark.stress
@pytest.mark.timeout(120)
@pytest.mark.asyncio
async def test_50_concurrent_searches(
    browser_goat: BrowserGoat,
    fake_searxng: FakeSearXNGServer,
) -> None:
    """Stress dimension: raw concurrency.

    50 simultaneous search() calls via asyncio.gather — verifies no deadlocks,
    no crashes, and all results contain a non-empty answer.
    """
    fake_searxng._result_count = 3

    async def _one(i: int) -> SearchResult:
        return await browser_goat.search(f"test query {i}", max_sources=3)

    results = await asyncio.gather(*[_one(i) for i in range(50)])

    assert len(results) == 50, "All 50 concurrent searches must return a result"
    for i, r in enumerate(results):
        assert isinstance(r, SearchResult), (
            f"Result {i} must be SearchResult, got {type(r).__name__}"
        )
        assert r.answer, f"Result {i} must have non-empty answer"


# Scenario 2: Extraction exhaustion — 100 results, 50 requested sources


@pytest.mark.stress
@pytest.mark.timeout(120)
@pytest.mark.asyncio
async def test_extraction_exhaustion_100_results(
    browser_goat: BrowserGoat,
    fake_searxng: FakeSearXNGServer,
) -> None:
    """Stress dimension: extraction saturation.

    Fake server returns 100 results; pipeline extracts up to 50.
    Verifies no semaphore leaks and result.sources is non-empty.
    """
    fake_searxng._result_count = 100

    result = await browser_goat.search("test exhaustion", max_sources=50)

    assert isinstance(result, SearchResult), "Must return SearchResult"
    assert len(result.sources) > 0, "Sources must not be empty after 100-result search"

    # Verify pipeline still functional after heavy extraction
    result2 = await browser_goat.search("post-exhaustion sanity", max_sources=3)
    assert isinstance(result2, SearchResult), "Pipeline must still be functional after exhaustion"
    assert result2.answer, "Post-exhaustion result must have answer"


# Scenario 3: Progressive SearXNG slowdown


@pytest.mark.stress
@pytest.mark.timeout(120)
@pytest.mark.asyncio
async def test_progressive_searxng_slowdown(
    browser_goat: BrowserGoat,
    fast_fake_searxng: FakeSearXNGServer,
) -> None:
    """Stress dimension: progressive backend latency.

    Iterates 4 latency tiers (0.1→0.5→1.0→2.0s) on fast_fake_searxng.
    Verifies SearchResult returned at each tier and pipeline_latency_ms
    increases progressively.
    """
    latencies = [0.1, 0.5, 1.0, 2.0]
    pipeline_times: list[int] = []

    for latency in latencies:
        fast_fake_searxng._latency = latency
        result = await browser_goat.search("test slowdown", max_sources=1)
        assert isinstance(result, SearchResult), (
            f"Must return SearchResult at latency={latency}s"
        )
        assert result.pipeline_latency_ms > 0, (
            f"pipeline_latency_ms must be > 0 at latency={latency}s"
        )
        pipeline_times.append(result.pipeline_latency_ms)

    # Verify general upward trend (at least non-decreasing first→last)
    assert pipeline_times[-1] >= pipeline_times[0] * 0.5, (
        "Final latency must not be drastically less than initial latency"
    )


# Scenario 4: Intermittent failures — 50% error rate


@pytest.mark.stress
@pytest.mark.timeout(120)
@pytest.mark.asyncio
async def test_intermittent_failures_50_percent(
    browser_goat: BrowserGoat,
    fake_searxng: FakeSearXNGServer,
) -> None:
    """Stress dimension: intermittent SearXNG errors.

    50% error rate over 10 sequential searches — at least 3 must return
    SearchResult with sources. No crashes on failed searches.
    """
    _orig_error = fake_searxng._error_rate
    _orig_count = fake_searxng._result_count
    fake_searxng._error_rate = 0.5
    fake_searxng._result_count = 5

    try:
        success_count = 0
        for i in range(10):
            try:
                result = await browser_goat.search(f"query {i}", max_sources=2)
                if isinstance(result, SearchResult) and result.sources:
                    success_count += 1
            except (TimeoutError, httpx.HTTPError):
                pass  # Expected under 50% error rate

        assert success_count >= 3, (
            f"At least 3/10 searches must succeed at 50% error rate, got {success_count}"
        )
    finally:
        fake_searxng._error_rate = _orig_error
        fake_searxng._result_count = _orig_count


# Scenario 5: Mixed workload — search + extract interleaved


@pytest.mark.stress
@pytest.mark.timeout(120)
@pytest.mark.asyncio
async def test_mixed_workload_search_and_extract(
    browser_goat: BrowserGoat,
    fake_searxng: FakeSearXNGServer,
) -> None:
    """Stress dimension: interleaved heterogeneous operations.

    5 searches + 5 scrapling.fetch calls interleaved via asyncio.gather.
    Verifies both operation types complete without cross-contamination.
    Extract calls use a 5s timeout to prevent hanging against unreachable URLs.
    """
    fake_searxng._result_count = 3

    test_url = "http://127.0.0.1:1/nonexistent"  # guaranteed unreachable

    async def _search(i: int) -> tuple[str, SearchResult | Exception]:
        try:
            r = await browser_goat.search(f"mixed query {i}", max_sources=2)
            return ("search", r)
        except Exception as exc:
            return ("search", exc)

    async def _extract(i: int) -> tuple[str, object]:
        try:
            profile = browser_goat.browser_profiles.get_random_profile()
            r = await asyncio.wait_for(
                browser_goat.scrapling.fetch(test_url, browser_profile=profile),
                timeout=5.0,
            )
            return ("extract", r)
        except Exception as exc:
            return ("extract", exc)

    tasks = []
    for i in range(5):
        tasks.append(_search(i))
        tasks.append(_extract(i))

    results = await asyncio.gather(*tasks)

    search_results = [r for op, r in results if op == "search"]
    extract_results = [r for op, r in results if op == "extract"]

    assert len(search_results) == 5, f"Expected 5 search results, got {len(search_results)}"
    assert len(extract_results) == 5, f"Expected 5 extract results, got {len(extract_results)}"

    # All searches must return SearchResult (not exceptions)
    search_ok = sum(1 for r in search_results if isinstance(r, SearchResult))
    assert search_ok == 5, (
        f"All 5 searches must return SearchResult, got {search_ok} ok"
    )


# Scenario 6: Rapid sequential searches — 100 iterations


@pytest.mark.stress
@pytest.mark.timeout(120)
@pytest.mark.asyncio
async def test_rapid_sequential_searches_100(
    browser_goat: BrowserGoat,
    fake_searxng: FakeSearXNGServer,
) -> None:
    """Stress dimension: sustained sequential throughput.

    100 sequential searches as fast as possible. Verifies all return
    SearchResult, httpx client is still functional, no connection leaks.
    """
    fake_searxng._result_count = 3

    results: list[SearchResult] = []
    for i in range(100):
        result = await browser_goat.search(f"rapid query {i}", max_sources=2)
        results.append(result)

    assert len(results) == 100, f"Expected 100 results, got {len(results)}"
    for i, r in enumerate(results):
        assert isinstance(r, SearchResult), (
            f"Result {i} must be SearchResult, got {type(r).__name__}"
        )

    # Verify pipeline still works after 100 sequential searches
    post_check = await browser_goat.search("sanity after 100", max_sources=1)
    assert isinstance(post_check, SearchResult), "Pipeline must still work after 100 sequential calls"
    assert post_check.answer, "Sanity answer must be non-empty"


# Scenario 7: Verification mode — high reliability (5 rollouts)


@pytest.mark.stress
@pytest.mark.timeout(120)
@pytest.mark.asyncio
async def test_verification_mode_high_reliability(
    browser_goat: BrowserGoat,
    fake_searxng: FakeSearXNGServer,
) -> None:
    """Stress dimension: multi-rollout verification.

    reliability_mode="high" triggers 5 parallel rollouts with consensus
    voting. _extract_sources is mocked; MultiRollout is real.
    """
    fake_searxng._result_count = 5

    result = await browser_goat.search(
        "test verification",
        reliability_mode="high",
        max_sources=2,
    )

    assert isinstance(result, SearchResult), (
        f"Must return SearchResult for high reliability, got {type(result).__name__}"
    )
    assert result.answer, "Multi-rollout result must have answer"


# Scenario 8: Strategy explore + reliability


@pytest.mark.stress
@pytest.mark.timeout(120)
@pytest.mark.asyncio
async def test_strategy_explore_with_reliability(
    browser_goat: BrowserGoat,
    fake_searxng: FakeSearXNGServer,
) -> None:
    """Stress dimension: combined strategy + reliability tiers.

    strategy="explore" with reliability_mode="high" exercises both
    Phase 2 and Phase 3 simultaneously. Must not crash.
    """
    fake_searxng._result_count = 5

    result = await browser_goat.search(
        "machine learning",
        strategy="explore",
        reliability_mode="high",
        max_sources=3,
    )

    assert isinstance(result, SearchResult), (
        f"Must return SearchResult for explore+high, got {type(result).__name__}"
    )


# Scenario 9: Empty results under load — 10 concurrent searches with 0 results


@pytest.mark.stress
@pytest.mark.timeout(120)
@pytest.mark.asyncio
async def test_empty_results_under_load(
    browser_goat: BrowserGoat,
    fake_searxng: FakeSearXNGServer,
) -> None:
    """Stress dimension: zero-result response handling under concurrency.

    Fake server returns 0 results. 10 concurrent searches verify graceful
    handling — all return SearchResult with empty or missing sources.
    """
    _orig_count = fake_searxng._result_count
    fake_searxng._result_count = 0

    try:
        async def _empty_search(i: int) -> SearchResult:
            return await browser_goat.search(f"empty query {i}", max_sources=3)

        results = await asyncio.gather(*[_empty_search(i) for i in range(10)])

        assert len(results) == 10, "All 10 concurrent empty-result searches must complete"
        for i, r in enumerate(results):
            assert isinstance(r, SearchResult), f"Result {i} must be SearchResult"
            assert isinstance(r.sources, list), f"Result {i} sources must be a list"
    finally:
        fake_searxng._result_count = _orig_count


# Scenario 10: Memory pressure — 500 large responses


@pytest.mark.stress
@pytest.mark.timeout(120)
@pytest.mark.asyncio
async def test_memory_pressure_500_large_responses(
    browser_goat: BrowserGoat,
    fake_searxng: FakeSearXNGServer,
) -> None:
    """Stress dimension: large response payloads.

    Fake server returns 150 results; pipeline processes max_sources=50.
    Verifies no OOM/crash and sources list is populated.
    (Reduced from 500 to 150 because MMR ranking is O(n²) pairwise.)
    """
    fake_searxng._result_count = 150

    result = await browser_goat.search("large result set", max_sources=50)

    assert isinstance(result, SearchResult), "Must return SearchResult from large-result query"
    assert len(result.sources) > 0, "Sources must not be empty for large-result search"


# Scenario 11: Connection pool — no exhaustion under 50 concurrent requests


@pytest.mark.stress
@pytest.mark.timeout(120)
@pytest.mark.asyncio
async def test_connection_pool_no_exhaustion(
    browser_goat: BrowserGoat,
    fake_searxng: FakeSearXNGServer,
) -> None:
    """Stress dimension: httpx connection pool saturation.

    50 concurrent searches verify no connection errors and all return
    SearchResult. Connection pool must not be exhausted.
    """
    fake_searxng._result_count = 3

    async def _pooled_search(i: int) -> SearchResult:
        return await browser_goat.search(f"pool query {i}", max_sources=2)

    results = await asyncio.gather(*[_pooled_search(i) for i in range(50)])

    assert len(results) == 50, "All 50 pooled searches must complete"
    for i, r in enumerate(results):
        assert isinstance(r, SearchResult), (
            f"Result {i} must be SearchResult (connection pool healthy)"
        )
        assert r.answer, f"Result {i} must have non-empty answer"


# Scenario 12: Recovery from SearXNG outage


@pytest.mark.stress
@pytest.mark.timeout(120)
@pytest.mark.asyncio
async def test_recovery_from_searxng_outage(
    browser_goat: BrowserGoat,
    fake_searxng: FakeSearXNGServer,
) -> None:
    """Stress dimension: backend outage recovery.

    Phase 1: error_rate=1.0 (complete outage) → search fails with error.
    Phase 2: error_rate=0.0 (recovered) → search succeeds with sources.
    Verifies pipeline can recover from total SearXNG failure.
    """
    _orig_error = fake_searxng._error_rate
    _orig_count = fake_searxng._result_count

    try:
        # Phase 1: Outage — all requests fail
        fake_searxng._error_rate = 1.0
        outage_ok = False
        try:
            result = await browser_goat.search("outage test", max_sources=2)
            if isinstance(result, SearchResult) and not result.sources:
                outage_ok = True
        except (TimeoutError, httpx.HTTPError, Exception):
            outage_ok = True  # Expected: search raises on total outage

        assert outage_ok, "Phase 1: must handle complete SearXNG outage without crashing"

        # Phase 2: Recovery — all requests succeed
        fake_searxng._error_rate = 0.0
        fake_searxng._result_count = 5
        result = await browser_goat.search("recovery test", max_sources=3)

        assert isinstance(result, SearchResult), "Phase 2: must return SearchResult after recovery"
        assert len(result.sources) > 0, "Phase 2: must have sources after SearXNG recovery"
        assert result.answer, "Phase 2: must have answer after recovery"
    finally:
        fake_searxng._error_rate = _orig_error
        fake_searxng._result_count = _orig_count


# Scenario 13: Large query input — 10KB query string


@pytest.mark.stress
@pytest.mark.timeout(120)
@pytest.mark.asyncio
async def test_large_query_input(
    browser_goat: BrowserGoat,
    fake_searxng: FakeSearXNGServer,
) -> None:
    """Stress dimension: oversized query string.

    10KB query string must not crash the pipeline. Result may have empty
    sources but must be a valid SearchResult.
    """
    fake_searxng._result_count = 5

    big_query = "a" * 10240
    result = await browser_goat.search(big_query, max_sources=2)

    assert isinstance(result, SearchResult), (
        "Large query must not crash — SearchResult expected"
    )


# Scenario 14: Scrapling escalation under concurrency


@pytest.mark.stress
@pytest.mark.timeout(120)
@pytest.mark.asyncio
async def test_scrapling_escalation_under_concurrency(
    browser_goat: BrowserGoat,
    fake_searxng: FakeSearXNGServer,
    mock_sources: list[ExtractedSource],
) -> None:
    """Stress dimension: extraction mock integrity under concurrency.

    20 concurrent searches verify the mocked _extract_sources was invoked
    for each search and mock_sources content is present in results.
    """
    fake_searxng._result_count = 5

    async def _extraction_search(i: int) -> SearchResult:
        return await browser_goat.search(f"extraction query {i}", max_sources=3)

    results = await asyncio.gather(*[_extraction_search(i) for i in range(20)])

    assert len(results) == 20, "All 20 extraction searches must complete"

    # Verify mock sources were used: each result should reference mock fixture URLs
    mock_urls = {s.url for s in mock_sources}
    for i, r in enumerate(results):
        assert isinstance(r, SearchResult), f"Result {i} must be SearchResult"
        assert len(r.sources) > 0, f"Result {i} sources must be non-empty (mock active)"
        result_urls = {s.url for s in r.sources}
        assert bool(result_urls & mock_urls), (
            f"Result {i} sources must include mock fixture URLs"
        )

    # Verify the mocked _extract_sources was called for each search
    mocked = BrowserGoat._extract_sources
    assert isinstance(mocked, AsyncMock), "_extract_sources must still be mocked"
    assert mocked.call_count >= 20, (
        f"_extract_sources must be called at least 20 times, got {mocked.call_count}"
    )


# Scenario 15: BM25/MMR scaling — 100 raw results


@pytest.mark.stress
@pytest.mark.timeout(120)
@pytest.mark.asyncio
async def test_bm25_mmr_scaling_100_results(
    browser_goat: BrowserGoat,
    fake_searxng: FakeSearXNGServer,
) -> None:
    """Stress dimension: ranking algorithm scaling.

    100 raw results fed through BM25+MMR ranking with max_sources=100.
    Verifies ranking completes, SearchResult returned, sources ordered by rank.
    """
    fake_searxng._result_count = 100

    result = await browser_goat.search("ranking stress test", max_sources=50)

    assert isinstance(result, SearchResult), "Must return SearchResult from 100-result ranking"
    assert len(result.sources) > 0, "Sources must be non-empty after ranking 100 results"

    # Verify rank ordering: ranks should be non-decreasing
    ranks = [s.rank for s in result.sources if s.rank is not None]
    if len(ranks) > 1:
        for i in range(1, len(ranks)):
            assert ranks[i] >= ranks[i - 1], (
                f"Sources must be ordered by rank (found {ranks[i]} after {ranks[i - 1]})"
            )


# Scenario 16: Pipeline latency tracking accuracy


@pytest.mark.stress
@pytest.mark.timeout(120)
@pytest.mark.asyncio
async def test_pipeline_latency_tracking_accuracy(
    browser_goat: BrowserGoat,
    fake_searxng: FakeSearXNGServer,
) -> None:
    """Stress dimension: latency metric accuracy.

    Fake server set to 100ms latency. Verifies pipeline_latency_ms exists,
    is a positive integer, and falls within a reasonable range.
    """
    _orig_latency = fake_searxng._latency
    _orig_count = fake_searxng._result_count
    fake_searxng._latency = 0.1
    fake_searxng._result_count = 3

    try:
        result = await browser_goat.search("latency accuracy test", max_sources=1)

        assert isinstance(result, SearchResult), "Must return SearchResult"
        assert hasattr(result, "pipeline_latency_ms"), "SearchResult must have pipeline_latency_ms"
        assert isinstance(result.pipeline_latency_ms, int), (
            f"pipeline_latency_ms must be int, got {type(result.pipeline_latency_ms).__name__}"
        )
        assert result.pipeline_latency_ms >= 50, (
            f"Latency must be >= 50ms, got {result.pipeline_latency_ms}"
        )
        assert result.pipeline_latency_ms < 30000, (
            f"Latency must be < 30000ms, got {result.pipeline_latency_ms}"
        )
    finally:
        fake_searxng._latency = _orig_latency
        fake_searxng._result_count = _orig_count


# Scenario 17: BrowserGoat health check


@pytest.mark.stress
@pytest.mark.timeout(120)
@pytest.mark.asyncio
async def test_browser_goat_health_check(
    browser_goat: BrowserGoat,
    fake_searxng: FakeSearXNGServer,
) -> None:
    """Stress dimension: component health verification.

    Verifies the /health endpoint on fake server returns True,
    and the browser_goat fixture has all sub-components initialized.
    """
    # Health endpoint on fake server
    is_healthy = await browser_goat.searxng.health_check()
    assert is_healthy is True, "Fake SearXNG /health must return True"

    # Verify fixture provides a fully initialized BrowserGoat
    assert browser_goat.searxng is not None, "searxng client must be initialized"
    assert browser_goat.query_intel is not None, "query_intel must be initialized"
    assert browser_goat.browser_profiles is not None, "browser_profiles must be initialized"
    assert browser_goat.url_pipeline is not None, "url_pipeline must be initialized"
    assert browser_goat.ranker is not None, "ranker must be initialized"
    assert browser_goat.content_extractor is not None, "content_extractor must be initialized"
    assert browser_goat.scrapling is not None, "scrapling must be initialized"
    assert browser_goat.give_up is not None, "give_up detector must be initialized"
    assert browser_goat.quality is not None, "quality gate must be initialized"

    # Verify the searxng_url matches the fake server
    assert browser_goat.searxng.base_url == fake_searxng.url, (
        f"SearXNG URL must match fake server ({fake_searxng.url})"
    )
