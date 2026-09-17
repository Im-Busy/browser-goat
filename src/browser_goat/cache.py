"""TTL-bounded HTML fetch cache.

Used to avoid re-fetching the same URL across multiple rollouts in
multi-rollout verification. Cache key is the normalized URL; cache value
is the raw HTML string. The cache is in-process, scoped to a single
``BrowserGoat`` instance, and bounded by both TTL and entry count.

Failure modes:
- Cache miss → fetch normally; cache the successful HTML response.
- Cache error (should not occur with the in-memory backend, but listed
  for completeness) → fall through to direct fetch; do not propagate.
"""

from __future__ import annotations

import math
import time
from collections import OrderedDict
from threading import Lock
from typing import Any


class TTLFetchCache:
    """In-memory TTL cache for fetched HTML.

    Stores ``(html, expiry_monotonic_ms)`` tuples in an ``OrderedDict``
    that doubles as an LRU. When ``max_entries`` is exceeded the
    least-recently-used entry is evicted. Entries whose TTL has elapsed
    are treated as misses and lazily purged on access.
    """

    def __init__(
        self,
        ttl_seconds: float = 900.0,
        max_entries: int = 256,
    ) -> None:
        """Initialize the TTL fetch cache.

        Args:
            ttl_seconds: Time-to-live per entry in seconds. Default 15 min.
            max_entries: Maximum entries before LRU eviction. Default 256.
        """
        if not math.isfinite(ttl_seconds) or ttl_seconds < 0 or max_entries < 0:
            raise ValueError("Cache TTL and capacity must be finite, non-negative values")
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._cache: OrderedDict[str, tuple[str, float]] = OrderedDict()
        self._lock = Lock()

        # Hit/miss counters for observability
        self.hits: int = 0
        self.misses: int = 0

    def get(self, url: str) -> str | None:
        """Return cached HTML for *url* or ``None`` on miss / expiry.

        Marks the entry as recently used. Lazy-purges expired entries.
        """
        with self._lock:
            entry = self._cache.get(url)
            if entry is None:
                self.misses += 1
                return None

            html, expiry = entry
            now = time.monotonic()
            if now >= expiry:
                # Expired — remove and report miss
                del self._cache[url]
                self.misses += 1
                return None

            # Touch: move to end for LRU recency
            self._cache.move_to_end(url)
            self.hits += 1
            return html

    def put(self, url: str, html: str) -> None:
        """Insert or refresh an entry.

        Evicts the least-recently-used entry when ``max_entries`` is
        exceeded.
        """
        with self._lock:
            expiry = time.monotonic() + self._ttl_seconds
            if url in self._cache:
                # Refresh in place and re-insert at end
                self._cache.move_to_end(url)
            self._cache[url] = (html, expiry)

            # Evict LRU entries if over capacity
            while len(self._cache) > self._max_entries:
                self._cache.popitem(last=False)

    def clear(self) -> None:
        """Drop all cached entries and reset counters."""
        with self._lock:
            self._cache.clear()
            self.hits = 0
            self.misses = 0

    def stats(self) -> dict[str, Any]:
        """Return observability counters for the cache."""
        with self._lock:
            total = self.hits + self.misses
            hit_rate = (self.hits / total) if total > 0 else 0.0
            return {
                "hits": self.hits,
                "misses": self.misses,
                "size": len(self._cache),
                "max_entries": self._max_entries,
                "ttl_seconds": self._ttl_seconds,
                "hit_rate": hit_rate,
            }
