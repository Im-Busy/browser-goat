"""Integration tests for browser-goat against real SearXNG.

These tests start browser-goat as subprocesses (CLI, HTTP serve, MCP stdio),
send real requests, validate responses, and clean up. They require a running
SearXNG instance at the URL specified by SEARXNG_URL env var (default localhost:8080).

Skip these tests with: pytest -m "not integration"
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx
import pytest

SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://localhost:8080")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
UV = "uv"


def _run_cli(*args: str, timeout: int = 120) -> tuple[int, str, str]:
    """Run browser-goat CLI and return (exit_code, stdout, stderr)."""
    result = subprocess.run(
        [UV, "run", "browser-goat", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
        cwd=str(PROJECT_ROOT),
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _cli_search_json(*args: str) -> dict[str, Any]:
    """Run CLI search and return parsed JSON."""
    code, stdout, stderr = _run_cli("search", *args)
    assert code == 0, f"CLI failed: {stderr}"
    return json.loads(stdout)


# ── CLI Integration Tests ──────────────────────────────────────────────────────


@pytest.mark.integration
class TestCLISearch:
    """End-to-end CLI search against real SearXNG."""

    def test_search_returns_results(self) -> None:
        result = _cli_search_json("Python programming language", "--max-sources", "3")
        assert "answer" in result
        assert "sources" in result
        assert len(result["sources"]) >= 1
        # Check source structure
        source = result["sources"][0]
        for field in ("url", "title", "rational", "evidence", "summary", "extraction_tier"):
            assert field in source, f"Missing field: {field}"

    def test_search_latency_under_30s(self) -> None:
        result = _cli_search_json("test query", "--max-sources", "1")
        assert result["pipeline_latency_ms"] < 30000, f"Too slow: {result['pipeline_latency_ms']}ms"

    def test_search_query_intent_detected(self) -> None:
        result = _cli_search_json("What is the capital of France?", "--max-sources", "2")
        assert result["query_intent"] in ("factual", "person", "temporal", "comparison", "howto", "research")

    def test_search_extraction_success_rate(self) -> None:
        result = _cli_search_json("news", "--max-sources", "3")
        assert result["extraction_success_rate"] >= 0.5

    def test_search_reliability_info(self) -> None:
        result = _cli_search_json("test", "--max-sources", "1")
        reliability = result["reliability"]
        assert "give_up_detected" in reliability
        assert "quality_passed" in reliability

    def test_search_with_time_range(self) -> None:
        result = _cli_search_json("AI", "--time-range", "week", "--max-sources", "2")
        assert result["total_sources_found"] >= 0

    def test_search_strategy_explore(self) -> None:
        result = _cli_search_json("machine learning", "--strategy", "explore", "--max-sources", "3")
        assert "sources" in result

    def test_search_empty_query_handled(self) -> None:
        code, _, _ = _run_cli("search", "", "--max-sources", "1")
        # Empty query may return results or error — either is acceptable
        assert code in (0, 1)

    def test_search_json_output_valid(self) -> None:
        result = _cli_search_json("hello world", "--max-sources", "1")
        # Verify top-level fields from SearchResult model
        expected_fields = {"answer", "sources", "query_intent", "engines_used",
                          "total_sources_found", "total_sources_used",
                          "extraction_success_rate", "pipeline_latency_ms",
                          "reliability", "timestamp"}
        found = set(result.keys())
        missing = expected_fields - found
        assert not missing, f"Missing SearchResult fields: {missing}"


# ── HTTP Serve Integration Tests ────────────────────────────────────────────────


@pytest.mark.integration
class TestHTTPServe:
    """End-to-end HTTP API tests against browser-goat serve."""

    @pytest.fixture(scope="class")
    def serve_port(self) -> int:
        return 18765  # avoid port conflicts

    @pytest.fixture(scope="class")
    def serve_process(self, serve_port: int) -> subprocess.Popen:
        """Start browser-goat serve as a background subprocess."""
        proc = subprocess.Popen(
            [UV, "run", "browser-goat", "serve",
             "--host", "127.0.0.1",
             "--port", str(serve_port),
             "--searxng-url", SEARXNG_URL],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(PROJECT_ROOT),
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        # Wait for server to be ready
        for _ in range(30):
            time.sleep(0.5)
            try:
                resp = httpx.get(f"http://127.0.0.1:{serve_port}/health", timeout=2)
                if resp.status_code == 200:
                    break
            except Exception:
                pass
        else:
            proc.terminate()
            proc.wait()
            pytest.fail("Serve process did not start within 15s")
        yield proc
        # Cleanup
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    def test_health_endpoint(self, serve_port: int, serve_process: subprocess.Popen) -> None:
        resp = httpx.get(f"http://127.0.0.1:{serve_port}/health", timeout=5)
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_search_endpoint_returns_results(self, serve_port: int, serve_process: subprocess.Popen) -> None:
        resp = httpx.post(
            f"http://127.0.0.1:{serve_port}/search",
            json={"query": "Python programming", "max_sources": 2},
            timeout=60,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "sources" in data
        assert len(data["sources"]) >= 1

    def test_search_endpoint_invalid_body(self, serve_port: int, serve_process: subprocess.Popen) -> None:
        """Non-JSON body should not hang — a disconnect or error is acceptable."""
        try:
            resp = httpx.post(
                f"http://127.0.0.1:{serve_port}/search",
                content=b"not json",
                timeout=5,
            )
            assert resp.status_code in (200, 400, 500)
        except httpx.RemoteProtocolError:
            pass  # disconnecting on bad input is also acceptable

    def test_404_on_unknown_path(self, serve_port: int, serve_process: subprocess.Popen) -> None:
        resp = httpx.get(f"http://127.0.0.1:{serve_port}/nonexistent", timeout=5)
        assert resp.status_code == 404


# ── MCP Server Integration Tests (in-process, via mcp.Client) ────────────────


@pytest.mark.integration
class TestMCPServer:

    def test_list_tools(self) -> None:
        """Verify search and extract tools are registered on the MCP server."""
        from browser_goat.mcp_server import create_mcp_server

        server = create_mcp_server(searxng_url=SEARXNG_URL)
        tool_names = {t.name for t in server._tool_manager._tools.values()}  # type: ignore[attr-defined]
        assert "search" in tool_names
        assert "extract" in tool_names

    def test_search_tool_registered(self) -> None:
        """Verify search tool exists in the FastMCP tool registry."""
        from browser_goat.mcp_server import create_mcp_server

        server = create_mcp_server(searxng_url=SEARXNG_URL)
        tool_names = [t.name for t in server._tool_manager._tools.values()]  # type: ignore[attr-defined]
        assert "search" in tool_names
        assert "extract" in tool_names

    def test_search_tool_callable(self) -> None:
        """Verify search tool function is callable with arguments."""
        from browser_goat.mcp_server import create_mcp_server

        server = create_mcp_server(searxng_url=SEARXNG_URL)
        search_fn = server._tool_manager._tools["search"].fn  # type: ignore[attr-defined]
        assert callable(search_fn)

        result = asyncio.run(search_fn(query="Python", max_sources=2))
        assert "sources" in result

    def test_extract_tool_callable(self) -> None:
        """Verify extract tool function is callable."""
        from browser_goat.mcp_server import create_mcp_server

        server = create_mcp_server(searxng_url=SEARXNG_URL)
        extract_fn = server._tool_manager._tools["extract"].fn  # type: ignore[attr-defined]
        assert callable(extract_fn)

        result = asyncio.run(extract_fn(url="https://example.com"))
        assert "url" in result
