"""Fake SearXNG HTTP server for isolated stress testing.

Provides a realistic SearXNG-compatible JSON API using raw asyncio TCP
(no web framework dependencies). Supports configurable latency injection,
deterministic fake result generation, and error simulation.

Usage:
    server = FakeSearXNGServer(latency=0.05, error_rate=0.1, result_count=20)
    await server.start()
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{server.url}/search", params={"q": "test"})
            data = resp.json()
    finally:
        await server.stop()
"""

from __future__ import annotations

import asyncio
import json
import random
import urllib.parse
from datetime import datetime, timedelta
from typing import Any

# ── Fake data constants ────────────────────────────────────────────────────────

_TOPICS: list[str] = [
    "quantum computing advances in 2026",
    "python asyncio best practices and patterns",
    "machine learning model deployment strategies",
    "postgresql query optimization techniques",
    "docker container orchestration with kubernetes",
    "rust programming language performance benchmarks",
    "typescript type system advanced patterns",
    "web scraping techniques and ethical considerations",
    "cloud native application architecture patterns",
    "distributed systems consensus algorithms explained",
    "react server components deep dive tutorial",
    "golang concurrency patterns and pitfalls",
    "cybersecurity threat detection with machine learning",
    "graphql vs rest api design comparison",
    "data engineering pipelines with apache spark",
    "linux kernel networking subsystem overview",
    "neural network pruning for edge deployment",
    "blockchain scalability solutions layer 2",
    "functional programming in modern javascript",
    "devops ci/cd pipeline optimization guide",
]

_SNIPPET_TEMPLATES: list[str] = [
    "A comprehensive guide exploring {topic} with practical examples and benchmarks. "
    "This article covers fundamental concepts, advanced techniques, and real-world "
    "applications that demonstrate the power and flexibility of modern approaches.",
    "Learn how {topic} can transform your workflow. Our in-depth analysis reveals "
    "key insights, performance characteristics, and implementation strategies that "
    "experienced practitioners rely on for production-grade systems.",
    "Discover the latest developments in {topic}. This thorough examination covers "
    "current best practices, common pitfalls to avoid, and emerging trends that "
    "are shaping the future of this rapidly evolving field.",
    "An authoritative reference on {topic}, featuring detailed code examples, "
    "architecture diagrams, and step-by-step walkthroughs. Suitable for both "
    "beginners and advanced users seeking to deepen their understanding.",
    "Everything you need to know about {topic}. From foundational principles to "
    "cutting-edge research, this resource provides actionable knowledge backed by "
    "empirical data and extensive testing across diverse scenarios.",
]

_ENGINES: list[str] = ["google", "bing", "duckduckgo", "brave", "wikipedia"]
_CATEGORIES: list[str] = ["general", "news", "science", "it"]

_ERROR_TYPES: list[str] = ["timeout", "500", "503", "close"]


# ── Server implementation ──────────────────────────────────────────────────────


class FakeSearXNGServer:
    """Async HTTP mock SearXNG server with configurable behavior.

    Serves realistic SearXNG-compatible JSON responses on localhost.
    Uses raw asyncio TCP — no aiohttp, starlette, or other web frameworks.

    Constructor args:
        latency: float seconds to delay each response (0 = instant).
        error_rate: float 0.0-1.0 probability of error per request.
        result_count: how many fake results to return per search.
        seed: int for deterministic random data generation.
    """

    def __init__(
        self,
        latency: float = 0.0,
        error_rate: float = 0.0,
        result_count: int = 10,
        seed: int = 42,
    ) -> None:
        self._latency = latency
        self._error_rate = error_rate
        self._result_count = result_count
        self._rng = random.Random(seed)
        self._base_date = datetime(2026, 1, 1)
        self._server: asyncio.AbstractServer | None = None
        self._port: int = 0

    # ── Public API ─────────────────────────────────────────────────────────

    @property
    def url(self) -> str:
        """Base URL of the running server (e.g. http://127.0.0.1:54321)."""
        return f"http://127.0.0.1:{self._port}"

    async def start(self) -> None:
        """Start the server on an OS-assigned port (port 0)."""
        self._server = await asyncio.start_server(
            self._handle_client, host="127.0.0.1", port=0
        )
        sock = self._server.sockets[0]
        sockname = sock.getsockname()
        assert isinstance(sockname, tuple) and len(sockname) == 2
        self._port = sockname[1]

    async def stop(self) -> None:
        """Stop the server and wait for pending connections to drain."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            self._port = 0

    # ── HTTP handler ───────────────────────────────────────────────────────

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle a single HTTP request (raw TCP, no framework)."""
        try:
            raw = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=30)
            request_line, *_ = raw.decode("utf-8", errors="replace").split("\r\n")
            method, path_and_query, *_ = request_line.split(" ") + ["", ""]
            path = path_and_query.split("?")[0]

            # ── Error injection (checked first) ──
            if self._error_rate > 0 and self._rng.random() < self._error_rate:
                await self._inject_error(writer)
                return

            # ── Simulated latency ──
            if self._latency > 0:
                await asyncio.sleep(self._latency)

            if method == "GET" and path in ("/health", "/config"):
                await self._respond_json(writer, 200, {"status": "ok"})
            elif method == "GET" and path == "/search":
                query = self._extract_query(path_and_query)
                await self._respond_search(writer, query)
            else:
                await self._respond_json(writer, 404, {"error": "not found"})

        except (TimeoutError, asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    # ── Error injection ────────────────────────────────────────────────────

    async def _inject_error(self, writer: asyncio.StreamWriter) -> None:
        """Inject a random error: timeout, 500, 503, or close connection."""
        error_type = self._rng.choice(_ERROR_TYPES)

        if error_type == "timeout":
            await asyncio.sleep(35.0)
            return  # falls through to finally → close

        if error_type == "close":
            return  # close immediately without response

        status = int(error_type)  # 500 or 503
        reason = {500: "Internal Server Error", 503: "Service Unavailable"}[status]
        body = json.dumps({"error": reason.lower().replace(" ", "_")}).encode()
        self._write_raw(
            writer,
            f"HTTP/1.1 {status} {reason}\r\n"
            f"Content-Type: application/json\r\n"
            "Connection: close\r\n"
            f"Content-Length: {len(body)}\r\n\r\n",
        )
        writer.write(body)
        await writer.drain()

    # ── Response helpers ───────────────────────────────────────────────────

    async def _respond_json(
        self, writer: asyncio.StreamWriter, status: int, data: dict[str, Any]
    ) -> None:
        """Send a JSON response with proper HTTP headers."""
        body = json.dumps(data).encode()
        reason = {200: "OK", 404: "Not Found"}.get(status, "OK")
        self._write_raw(
            writer,
            f"HTTP/1.1 {status} {reason}\r\n"
            f"Content-Type: application/json\r\n"
            "Connection: close\r\n"
            f"Content-Length: {len(body)}\r\n\r\n",
        )
        writer.write(body)
        await writer.drain()

    async def _respond_search(
        self, writer: asyncio.StreamWriter, query: str
    ) -> None:
        """Send a SearXNG-compatible search response."""
        results = self._generate_results(query)
        data: dict[str, Any] = {
            "query": query,
            "number_of_results": len(results),
            "results": results,
        }
        await self._respond_json(writer, 200, data)

    # ── Fake data generation ───────────────────────────────────────────────

    def _generate_results(self, query: str) -> list[dict[str, Any]]:
        """Generate deterministic fake search results matching SearXNG format."""
        results: list[dict[str, Any]] = []
        for i in range(self._result_count):
            topic = self._rng.choice(_TOPICS)
            # Inject query terms into title for realism
            if len(query) > 3 and i < self._result_count // 2:
                topic = f"{query} — {topic}"

            title = f"Result {i + 1}: {topic}"
            domain = f"https://example{i % 5}.com"
            path_segments = topic.lower().replace(" ", "-").replace(".", "")[:40]
            url = f"{domain}/{path_segments}"

            snippet = self._rng.choice(_SNIPPET_TEMPLATES).format(topic=topic)
            snippet = snippet[: self._rng.randint(50, 150)]

            engine = _ENGINES[i % len(_ENGINES)]
            category = _CATEGORIES[i % len(_CATEGORIES)]
            score = round(self._rng.random(), 3)
            pub_date = (
                self._base_date + timedelta(days=self._rng.randint(0, 180))
            ).strftime("%Y-%m-%d")

            results.append({
                "title": title,
                "url": url,
                "content": snippet,
                "engine": engine,
                "score": score,
                "category": category,
                "parsed_url": [url],
                "publishedDate": pub_date,
            })
        return results

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_query(path_and_query: str) -> str:
        """Extract the 'q' parameter from the request path+query."""
        parsed = urllib.parse.urlparse(path_and_query)
        params = urllib.parse.parse_qs(parsed.query)
        queries = params.get("q", [""])
        return queries[0] if queries else ""

    @staticmethod
    def _write_raw(writer: asyncio.StreamWriter, data: str) -> None:
        """Write a raw string to the stream writer."""
        writer.write(data.encode())
