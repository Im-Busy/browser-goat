"""Tests for the TTL-bounded HTML fetch cache."""

from __future__ import annotations

import time

from browser_goat.cache import TTLFetchCache


class TestTTLFetchCache:
    def test_miss_returns_none(self) -> None:
        cache: TTLFetchCache = TTLFetchCache()
        assert cache.get("https://example.com") is None

    def test_put_and_get(self) -> None:
        cache: TTLFetchCache = TTLFetchCache()
        cache.put("https://example.com", "<html>hi</html>")
        assert cache.get("https://example.com") == "<html>hi</html>"

    def test_expiry(self) -> None:
        cache: TTLFetchCache = TTLFetchCache(ttl_seconds=0.05)
        cache.put("https://example.com", "<html>hi</html>")
        time.sleep(0.1)
        assert cache.get("https://example.com") is None

    def test_lru_eviction(self) -> None:
        cache: TTLFetchCache = TTLFetchCache(ttl_seconds=60.0, max_entries=2)
        cache.put("a", "1")
        cache.put("b", "2")
        cache.put("c", "3")  # evicts "a" (oldest)
        assert cache.get("a") is None
        assert cache.get("b") == "2"
        assert cache.get("c") == "3"

    def test_get_touches_lru(self) -> None:
        cache: TTLFetchCache = TTLFetchCache(ttl_seconds=60.0, max_entries=2)
        cache.put("a", "1")
        cache.put("b", "2")
        # Touch "a" so it becomes most-recently-used
        assert cache.get("a") == "1"
        cache.put("c", "3")  # would have evicted "a", but "a" was just touched
        assert cache.get("a") == "1"
        assert cache.get("b") is None

    def test_stats_counters(self) -> None:
        cache: TTLFetchCache = TTLFetchCache()
        cache.put("a", "1")
        cache.get("a")  # hit
        cache.get("b")  # miss
        stats = cache.stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["size"] == 1
        assert stats["hit_rate"] == 0.5

    def test_clear_resets_counters(self) -> None:
        cache: TTLFetchCache = TTLFetchCache()
        cache.put("a", "1")
        cache.get("a")
        cache.clear()
        # After clear, even a get that misses does not count toward misses=0
        # because clear already reset the counter. Put a fresh entry so the
        # subsequent get can succeed.
        cache.put("a", "1")
        assert cache.get("a") == "1"
        # Counters reset by clear(); only the post-clear hit is recorded.
        assert cache.stats()["hits"] == 1
        assert cache.stats()["misses"] == 0

    def test_overwrite_refreshes_ttl(self) -> None:
        cache: TTLFetchCache = TTLFetchCache(ttl_seconds=0.05)
        cache.put("a", "first")
        time.sleep(0.03)
        cache.put("a", "second")  # reset TTL
        time.sleep(0.03)
        # Original TTL would have expired; the refresh extended it
        assert cache.get("a") == "second"

    def test_thread_safety(self) -> None:
        """Concurrent puts and gets should not corrupt state.

        Four writers each push 50 unique URLs to ranges
        ``u0..u49``, ``u100..u149``, ``u200..u249``, ``u300..u349``.
        All 200 URLs should be retrievable after the writers join.
        """
        import threading

        # max_entries=500 covers all 200 unique URLs without LRU eviction.
        cache: TTLFetchCache = TTLFetchCache(max_entries=500)
        errors: list[Exception] = []

        writer_ranges = [(0, 50), (100, 150), (200, 250), (300, 350)]

        def writer(start: int, stop: int) -> None:
            try:
                for i in range(start, stop):
                    cache.put(f"u{i}", f"v{i}")
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        threads = [
            threading.Thread(target=writer, args=(start, stop))
            for start, stop in writer_ranges
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        # All 200 unique URLs across the four ranges should be present.
        for start, stop in writer_ranges:
            for i in range(start, stop):
                assert cache.get(f"u{i}") == f"v{i}"
