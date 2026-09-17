"""Shared pytest fixtures for stress testing the BrowserGoat pipeline.

Provides session-scoped FakeSearXNGServer, mock extraction sources,
and a function-scoped BrowserGoat connected to the fake server.
"""

from __future__ import annotations

import asyncio
import random
import threading
from collections.abc import AsyncIterator, Generator
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

from browser_goat.models import ExtractedSource
from browser_goat.router import BrowserGoat

if TYPE_CHECKING:
    from tests.load.fake_searxng import FakeSearXNGServer


# ── Session-scoped fake SearXNG server ─────────────────────────────────────────


@pytest.fixture(scope="session")
def fake_searxng() -> Generator[FakeSearXNGServer]:
    """Session-scoped fake SearXNG server on a random port.

    Started once per test session, shared across all load tests.
    Yields the server instance so tests can reconfigure latency/error_rate.

    The server's asyncio event loop runs in a background daemon thread
    so it can process connections from pytest's main event loop.
    """
    from tests.load.fake_searxng import FakeSearXNGServer as _Server

    server = _Server(latency=0.01, seed=42)

    loop = asyncio.new_event_loop()
    loop.run_until_complete(server.start())

    # Keep the event loop alive in a background thread to process connections
    ready = threading.Event()

    def _run_loop() -> None:
        asyncio.set_event_loop(loop)
        ready.set()
        loop.run_forever()

    thread = threading.Thread(target=_run_loop, daemon=True, name="fake-searxng-loop")
    thread.start()
    ready.wait()  # ensure loop is running before yielding

    yield server

    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=10)
    loop.run_until_complete(server.stop())
    loop.close()


# ── Mock extraction sources ────────────────────────────────────────────────────


@pytest.fixture
def mock_sources() -> list[ExtractedSource]:
    """Function-scoped list of realistic ExtractedSource objects.

    Reuses the pattern from tests/test_router.py mock_sources fixture.
    These stand in for real Scrapling extraction so the full pipeline
    runs without external HTTP calls.
    """
    return [
        ExtractedSource(
            url="https://example1.com/test",
            title="Test Result 1",
            rational="Provides definitive reference for the query.",
            evidence="Detailed evidence from test source 1 explaining the topic.",
            summary="Test source 1 covers the topic comprehensively.",
            extraction_tier=2,
            used_scrapling=False,
            rank=1,
            final_score=0.95,
            engine="google",
        ),
        ExtractedSource(
            url="https://example2.com/test",
            title="Test Result 2",
            rational="Corroborates findings from source 1 with additional data.",
            evidence="Supplementary evidence from test source 2.",
            summary="Test source 2 adds context and expands coverage.",
            extraction_tier=2,
            used_scrapling=False,
            rank=2,
            final_score=0.85,
            engine="bing",
        ),
        ExtractedSource(
            url="https://example3.com/test",
            title="Test Result 3",
            rational="Offers an alternative perspective on the query.",
            evidence="Contrasting evidence from test source 3.",
            summary="Test source 3 provides a different angle.",
            extraction_tier=2,
            used_scrapling=False,
            rank=3,
            final_score=0.75,
            engine="duckduckgo",
        ),
    ]


# ── BrowserGoat fixture (connected to fake server) ─────────────────────────────


@pytest.fixture
async def browser_goat(
    fake_searxng: FakeSearXNGServer,
    mock_sources: list[ExtractedSource],
) -> AsyncIterator[BrowserGoat]:
    """Function-scoped BrowserGoat wired to the fake SearXNG server.

    Patches _extract_sources so the full pipeline runs without real
    Scrapling — all results come from the mock_sources fixture.
    Each test gets a fresh BrowserGoat instance.
    """
    with patch.object(
        BrowserGoat,
        "_extract_sources",
        new=AsyncMock(return_value=(mock_sources, mock_sources, 1.0)),
    ):
        meta = BrowserGoat(searxng_url=fake_searxng.url)
        try:
            yield meta
        finally:
            await meta.close()


# ── Fast variant (0ms latency) ─────────────────────────────────────────────────


@pytest.fixture
def fast_fake_searxng(
    fake_searxng: FakeSearXNGServer,
) -> Generator[FakeSearXNGServer]:
    """Function-scoped fixture wrapping session fake_searxng with 0ms latency.

    Temporarily overrides _latency to 0 for rapid-response tests,
    then restores the original value after the test.
    """
    original = fake_searxng._latency
    fake_searxng._latency = 0.0
    yield fake_searxng
    fake_searxng._latency = original


@pytest.fixture(autouse=True)
def reset_server(fake_searxng: FakeSearXNGServer) -> None:
    """Prevent one load scenario's mutations from leaking into the next."""
    fake_searxng._latency = 0.01
    fake_searxng._error_rate = 0.0
    fake_searxng._result_count = 10
    fake_searxng._rng = random.Random(42)


# ── Auto-marker hook ───────────────────────────────────────────────────────────


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Auto-apply 'stress' marker to every test in tests/load/."""
    for item in items:
        if item.path.as_posix().startswith("tests/load/"):
            item.add_marker(pytest.mark.stress)
