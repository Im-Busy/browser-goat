"""Full-path smoke tests using a local SearXNG-shaped HTTP fixture, not real engines."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from browser_goat.api import create_server
from browser_goat.extraction.scrapling_fetcher import ScraplingFetcher
from browser_goat.mcp_server import create_mcp_server
from browser_goat.router import BrowserGoat

ROOT = Path(__file__).resolve().parents[1]
TEXT = "Python asyncio provides an event loop for concurrent tasks and asynchronous input and output. " * 24


@pytest.fixture
def local_backend() -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            base = f"http://127.0.0.1:{self.server.server_port}"
            if self.path.startswith("/search"):
                body = json.dumps({"results": [
                    {"url": f"{base}/page/{i}", "title": "Python asyncio", "content": TEXT, "engine": "google"}
                    for i in range(3)
                ]}).encode()
                content_type = "application/json"
            elif self.path == "/config":
                body, content_type = b'{"engines":[]}', "application/json"
            else:
                body = f"<html><title>Python asyncio</title><article><p>{TEXT}</p></article></html>".encode()
                content_type = "text/html"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("strategy", ["default", "direct", "auto", "explore", "decompose"])
@pytest.mark.parametrize("reliability", ["standard", "high", "maximum", "auto"])
async def test_library_strategy_reliability_matrix(local_backend: str, strategy: str, reliability: str) -> None:
    async with BrowserGoat(local_backend) as goat:
        result = await goat.search("Python asyncio", strategy=strategy, reliability_mode=reliability, max_sources=1)
        assert len(result.sources) == 1
        assert result.reliability.quality_passed
        assert result.total_sources_used == len(result.sources)
        if reliability in ("high", "maximum"):
            assert result.verification.rollout_count >= 4
        await goat.extract(f"{local_backend}/page/0")
        await goat.extract(f"{local_backend}/page/0")
        assert goat.cache_stats()["hits"] >= 1
        goat.clear_cache()
        assert goat.cache_stats()["size"] == 0


@pytest.mark.parametrize("command", ["search", "extract", "verify"])
@pytest.mark.parametrize("fmt", ["json", "pretty"])
async def test_cli_local_full_path(local_backend: str, command: str, fmt: str) -> None:
    query = f"{local_backend}/page/0" if command == "extract" else "Python asyncio"
    args = [command, query, "--searxng-url", local_backend, "--format", fmt]
    if command == "verify":
        args += ["--rollouts", "3"]
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "browser_goat.cli", *args,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "BROWSER_GOAT_LLM": "", "PYTHONIOENCODING": "utf-8"},
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
    assert proc.returncode == 0, stderr.decode()
    data = json.loads(stdout)
    if command == "extract":
        assert len(data["text"]) > 1000
    elif command == "verify":
        assert data["rollouts_run"] == 3
        assert data["verification"]["is_consensus"] is False
        assert data["answer"] != "No consensus reached."
    else:
        assert data["sources"]


async def test_http_adapter_and_errors(local_backend: str) -> None:
    async with BrowserGoat(local_backend) as goat:
        server = await create_server(goat, "127.0.0.1", 0)
        async with server, httpx.AsyncClient(base_url=f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}") as client:
            assert (await client.get("/health")).json() == {"status": "ok"}
            assert (await client.get("/missing")).status_code == 404
            for body in ([], {"query": ""}, {"query": "x", "max_sources": 0}):
                response = await client.post("/search", json=body)
                assert response.status_code == 400 and response.json()["error"]
            assert (await client.post("/search", content="not JSON")).status_code == 400
            assert (await client.post("/search", content="x" * 65537)).status_code == 413
            response = await client.post("/search", json={"query": "Python", "max_sources": 1, "language": "fr"})
            assert response.status_code == 200
            assert len(response.json()["sources"]) == 1
            with patch.object(goat.searxng, "search", AsyncMock(side_effect=httpx.ConnectError("backend down"))):
                assert (await client.post("/search", json={"query": "Python"})).status_code == 502


@pytest.mark.parametrize("wrapper", [False, True], ids=["python-stdio", "npm-stdio"])
async def test_mcp_stdio_all_tools(local_backend: str, wrapper: bool) -> None:
    if wrapper and not shutil.which("node"):
        pytest.skip("Node.js is not installed")
    params = StdioServerParameters(
        command="node" if wrapper else sys.executable,
        args=[str(ROOT / "npm/index.js")] if wrapper else ["-m", "browser_goat.mcp_server"],
        env={**os.environ, "PYTHON_CMD": sys.executable, "SEARXNG_URL": local_backend, "BROWSER_GOAT_LLM": ""},
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        tools = await session.list_tools()
        assert {t.name for t in tools.tools} == {"search", "extract", "verify"}
        for name, arguments in [
            ("search", {"query": "Python", "max_sources": 1, "strategy": "direct"}),
            ("extract", {"url": f"{local_backend}/page/0"}),
            ("verify", {"query": "Python", "rollouts": 3}),
            ("verify", {"query": "Python", "rollouts": 6, "searxng_url": local_backend}),
        ]:
            result = await session.call_tool(name, arguments)
            assert not result.isError, result
            assert result.structuredContent
        bad = await session.call_tool("search", {"query": "Python", "max_sources": 0})
        assert bad.isError


async def test_mcp_server_instances_do_not_share_backend() -> None:
    with patch("browser_goat.mcp_server.BrowserGoat") as factory:
        first, second = AsyncMock(), AsyncMock()
        first.extract.return_value = {"url": "first"}
        second.extract.return_value = {"url": "second"}
        factory.side_effect = [first, second]
        server = create_mcp_server("http://127.0.0.1:1")
        create_mcp_server("http://127.0.0.1:2")
        await server.call_tool("extract", {"url": "https://example.com"})
        first.extract.assert_awaited_once()
        second.extract.assert_not_awaited()


async def test_decomposition_uses_chat_callback_and_leaf_results(local_backend: str) -> None:
    async def llm(messages: list[dict[str, Any]]) -> str:
        prompt = messages[0]["content"]
        if "decomposition analyzer" in prompt:
            return json.dumps({"can_answer_directly": "Original" not in prompt})
        if "decomposition system" in prompt:
            return '[{"id":"a","query":"Python tasks","dependencies":[]},{"id":"b","query":"Python loop","dependencies":["a"]}]'
        if "research assistant" in prompt:
            return json.dumps({"rational": "Relevant", "evidence": TEXT, "summary": TEXT[:180]})
        return "[1] " + TEXT[:180]

    encoding = MagicMock()
    encoding.encode.side_effect = lambda text: list(text)
    encoding.decode.side_effect = lambda tokens: "".join(tokens)
    # Only the chat callback and token budget are simulated; search/fetch are real local HTTP.
    with patch("tiktoken.get_encoding", return_value=encoding):
        async with BrowserGoat(local_backend, llm_call=llm) as goat:
            result = await goat.search("Original Python question", strategy="decompose", max_sources=1)
            assert result.sources and result.total_sources_found == 6
            assert result.answer.startswith("[1]")


@pytest.mark.browser_local
@pytest.mark.parametrize("tier", ["scrapling", "crawl4ai", "playwright"])
async def test_real_browser_on_local_page(local_backend: str, tier: str) -> None:
    """No search engines, challenge bypass, or external target pages are exercised."""
    fetcher = ScraplingFetcher(timeout=10)
    try:
        operation = getattr(fetcher, f"_try_{tier}")(f"{local_backend}/page/0")
        result = await asyncio.wait_for(operation, timeout=30)
        assert result.success, result.error
        assert "Python asyncio" in result.html
    finally:
        await fetcher.close()
