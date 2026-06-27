"""CLI entry point for browser-goat.

Usage:
    browser-goat search "What is Python?" --searxng-url http://localhost:8080
    browser-goat search "latest AI news" --time-range week --strategy explore
    browser-goat search "Python vs Rust" --reliability high
    uvx browser-goat search "quantum computing research"
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from browser_goat.router import BrowserGoat

GUIDE_TEXT = r"""
================================================================================
                       browser-goat -- Usage Guide
================================================================================

QUICK START
-----------
  uvx browser-goat search "latest AI research"
  uvx browser-goat extract "https://example.com/article"
  npx browser-goat              (MCP server for AI agents -- see CLIENTS.md)


SUBCOMMANDS
-----------
  search    Run the full 6-layer search pipeline
  extract   Fetch and extract content from a single URL
  verify    Verify an answer via multi-rollout voting
  serve     Run as an HTTP JSON API server
  service   Manage the background service (status / start / stop)


SEARCH FLAGS
------------
  query                  Search query string (positional, required)
  --searxng-url URL      SearXNG instance URL (default: http://localhost:8080)
  --engines ENGINE ...   SearXNG engines to use (e.g. google bing scholar)
  --time-range RANGE     Time filter: day / week / month / year
  --language LANG        Language code (default: en)
  --max-sources N        Max sources to extract (default: 15)
  --strategy MODE        Search strategy (see below)
  --reliability MODE     Reliability mode (see below)
  --format MODE          Output format: json / pretty (default: json)


EXTRACT FLAGS
-------------
  url                    URL to extract content from (positional, required)
  --searxng-url URL      SearXNG instance URL
  --format MODE          Output format: json / pretty


VERIFY FLAGS
------------
  query                  Query to verify (positional, required)
  --searxng-url URL      SearXNG instance URL
  --rollouts N           Number of parallel rollouts (default: 5)
  --format MODE          Output format: json / pretty


SERVE FLAGS
-----------
  --host HOST            Host to bind to (default: 0.0.0.0)
  --port PORT            Port to listen on (default: 8000)
  --searxng-url URL      SearXNG instance URL


SERVICE FLAGS
-------------
  status                 Check if both services are healthy
    --searxng-url URL
  start                  Start browser-goat serve in background
    --port PORT          (default: 8000)
    --searxng-url URL
  stop                   Stop the background service
    --searxng-url URL    (ignored for stop, accepted for consistency)


STRATEGY MODES
--------------
  default    Standard single-pass search with all layers active.
             Best for simple factual queries and general use.

  explore    Adaptive multi-angle exploration. Expands the query into
             multiple perspectives, searches each, and synthesizes
             results. Best for research, comparisons, and open-ended
             questions.

  decompose  Recursive decomposition for complex queries. Breaks the
             query into sub-questions, answers each recursively, and
             aggregates results. Best for multi-faceted questions that
             span multiple domains.


RELIABILITY MODES
-----------------
  standard   Single search pass with quality gate. The answer must pass
             minimum thresholds (length, citations) or retry once.

  high       5 parallel searches with consensus voting. Results are
             voted on across 5 parallel search passes. Best for
             questions where accuracy matters.

  maximum    8 parallel searches with consensus voting + LLM
             tie-breaking. Results are voted on across 8 parallel
             search passes; ties broken by LLM verification. Best
             for high-stakes questions or downstream agent
             consumption.


MCP TOOLS
---------
  search     Full pipeline: intent detection -> SearXNG -> hybrid ranking
             -> extraction -> reliability -> answer.
             Accepts time_range, max_sources, strategy parameters.

  extract    Fetch and extract a single URL with anti-bot bypass
             (Cloudflare Turnstile). Returns structured content.


LIBRARY USAGE
-------------
  from browser_goat import BrowserGoat

  meta = BrowserGoat(searxng_url="http://localhost:8080")
  result = await meta.search("quantum computing")
  print(result.answer)


DOCKER
------
  docker compose up
      SearXNG at http://localhost:8082
      browser-goat API at http://localhost:8000


EXAMPLES
--------
  # Simple fact lookup
  uvx browser-goat search "capital of Brazil"

  # Recent news with time filter
  uvx browser-goat search "Gemini 3 release" --time-range week

  # Research query with adaptive exploration
  uvx browser-goat search "Rust vs Zig for systems programming" --strategy explore

  # High-stakes query with maximum reliability
  uvx browser-goat search "latest clinical trial results diabetes" --reliability maximum

  # Extract a page with anti-bot bypass
  uvx browser-goat extract "https://en.wikipedia.org/wiki/SearXNG"

  # Verify an answer with 7 rollouts
  uvx browser-goat verify "What is the GDP of France?" --rollouts 7

  # Run as HTTP API server
  uvx browser-goat serve --port 8000

  # Manage background service
  uvx browser-goat service start
  uvx browser-goat service status
  uvx browser-goat service stop


ENVIRONMENT
-----------
  SEARXNG_URL    SearXNG instance URL (overrides --searxng-url defaults)


MCP CONFIGURATION
-----------------
  See CLIENTS.md in the project root for platform-specific MCP config
  snippets for Claude Desktop, Cursor/VS Code, OpenCode, GitHub Copilot,
  and Windsurf.
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="browser-goat",
        description="Meta-layer search intelligence wrapping SearXNG",
    )
    parser.add_argument(
        "--guide",
        action="store_true",
        help="Print comprehensive usage guide and exit",
    )
    sub = parser.add_subparsers(dest="command")

    # ── search ──
    search = sub.add_parser("search", help="Run a full search pipeline")
    search.add_argument("query", help="Search query string")
    search.add_argument(
        "--searxng-url",
        default="http://localhost:8080",
        help="SearXNG instance URL (default: http://localhost:8080)",
    )
    search.add_argument(
        "--engines",
        nargs="*",
        default=None,
        help="SearXNG engines to use (e.g. google bing scholar)",
    )
    search.add_argument(
        "--time-range",
        choices=["day", "week", "month", "year"],
        default=None,
        help="Time filter for results",
    )
    search.add_argument(
        "--language",
        default="en",
        help="Language code for results (default: en)",
    )
    search.add_argument(
        "--max-sources",
        type=int,
        default=15,
        help="Maximum sources to extract (default: 15)",
    )
    search.add_argument(
        "--strategy",
        choices=["default", "auto", "explore", "decompose"],
        default="default",
        help="Search strategy (default: default)",
    )
    search.add_argument(
        "--reliability",
        choices=["standard", "high", "maximum"],
        default="standard",
        help="Reliability mode (default: standard)",
    )
    search.add_argument(
        "--format",
        choices=["json", "pretty"],
        default="json",
        help="Output format (default: json)",
    )

    # ── extract ──
    extract = sub.add_parser("extract", help="Extract content from a URL")
    extract.add_argument("url", help="URL to extract content from")
    extract.add_argument(
        "--searxng-url",
        default="http://localhost:8080",
        help="SearXNG instance URL",
    )
    extract.add_argument(
        "--format",
        choices=["json", "pretty"],
        default="json",
        help="Output format (default: json)",
    )

    # ── verify ──
    verify = sub.add_parser("verify", help="Verify an answer via multi-rollout voting")
    verify.add_argument("query", help="The query to verify")
    verify.add_argument(
        "--searxng-url",
        default="http://localhost:8080",
        help="SearXNG instance URL",
    )
    verify.add_argument(
        "--rollouts",
        type=int,
        default=5,
        help="Number of parallel rollouts (default: 5)",
    )
    verify.add_argument(
        "--format",
        choices=["json", "pretty"],
        default="json",
        help="Output format (default: json)",
    )

    # ── serve ──
    serve = sub.add_parser("serve", help="Run browser-goat as an HTTP JSON API server")
    serve.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)",
    )
    serve.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to listen on (default: 8000)",
    )
    serve.add_argument(
        "--searxng-url",
        default="http://localhost:8080",
        help="SearXNG instance URL (default: http://localhost:8080)",
    )

    # ── service ──
    service = sub.add_parser("service", help="Manage the browser-goat background service")
    svc_sub = service.add_subparsers(dest="svc_command", required=True)

    svc_status = svc_sub.add_parser("status", help="Check if both services are healthy")
    svc_status.add_argument(
        "--searxng-url",
        default="http://localhost:8080",
        help="SearXNG instance URL (default: http://localhost:8080)",
    )

    svc_start = svc_sub.add_parser("start", help="Start browser-goat serve in background")
    svc_start.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to listen on (default: 8000)",
    )
    svc_start.add_argument(
        "--searxng-url",
        default="http://localhost:8080",
        help="SearXNG instance URL (default: http://localhost:8080)",
    )

    svc_stop = svc_sub.add_parser("stop", help="Stop the background browser-goat service")
    svc_stop.add_argument(
        "--searxng-url",
        default="http://localhost:8080",
        help="SearXNG instance URL (ignored for stop)",
    )

    return parser


def format_output(data: Any, fmt: str) -> str:
    """Format output as JSON or pretty-printed."""
    if fmt == "pretty":
        if hasattr(data, "model_dump"):
            return json.dumps(data.model_dump(), indent=2, ensure_ascii=False)
        return json.dumps(data, indent=2, ensure_ascii=False)
    if hasattr(data, "model_dump"):
        return str(data.model_dump_json())
    return json.dumps(data, ensure_ascii=False)


async def cmd_search(args: argparse.Namespace) -> None:
    meta = BrowserGoat(searxng_url=args.searxng_url)
    result = await meta.search(
        query=args.query,
        engines=args.engines,
        time_range=args.time_range,
        language=args.language,
        max_sources=args.max_sources,
        strategy=args.strategy,
        reliability_mode=args.reliability,
    )
    output = format_output(result, args.format)
    print(output)


async def cmd_extract(args: argparse.Namespace) -> None:
    meta = BrowserGoat(searxng_url=args.searxng_url)
    fetcher = meta.scrapling
    extractor = meta.content_extractor
    profile = meta.browser_profiles.get_random_profile()

    fetch_result = await fetcher.fetch(args.url, profile)
    if not fetch_result.success:
        print(json.dumps({"error": fetch_result.error or "fetch failed"}), file=sys.stderr)
        sys.exit(1)

    content = extractor.extract(fetch_result.html, args.url)

    output = format_output(
        {
            "url": args.url,
            "title": content.title,
            "text": content.text[:1000] + "..." if len(content.text) > 1000 else content.text,
            "extraction_tier": content.extraction_tier,
            "text_length": len(content.text),
        },
        args.format,
    )
    print(output)


async def cmd_verify(args: argparse.Namespace) -> None:
    meta = BrowserGoat(searxng_url=args.searxng_url)
    result = await meta.search(
        query=args.query,
        reliability_mode="high" if args.rollouts <= 5 else "maximum",
    )
    output = format_output(result, args.format)
    print(output)


async def cmd_serve(args: argparse.Namespace) -> None:
    """Run browser-goat as a minimal HTTP JSON API server (zero extra deps)."""
    meta = BrowserGoat(searxng_url=args.searxng_url)

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            raw = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=30)
            request_line, *_ = raw.decode("utf-8", errors="replace").split("\r\n")
            method, path, *_ = request_line.split(" ") + ["", ""]

            if method == "GET" and path in ("/health", "/"):
                body = b'{"status":"ok"}'
                writer.write(
                    b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                    b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
                )
                await writer.drain()
                return

            if method == "POST" and path == "/search":
                content_length = 0
                for line in raw.decode("utf-8", errors="replace").split("\r\n"):
                    if line.lower().startswith("content-length:"):
                        content_length = int(line.split(":")[1].strip())
                body_raw = await asyncio.wait_for(reader.readexactly(content_length), timeout=5)
                params = json.loads(body_raw)

                result = await meta.search(
                    query=params.get("query", ""),
                    time_range=params.get("time_range"),
                    max_sources=params.get("max_sources", 15),
                    strategy=params.get("strategy", "default"),
                    reliability_mode=params.get("reliability", "standard"),
                )
                body = result.model_dump_json().encode()
                writer.write(
                    b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                    b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
                )
                await writer.drain()
                return

            body = b'{"error":"not found"}'
            writer.write(
                b"HTTP/1.1 404 Not Found\r\nContent-Type: application/json\r\n"
                b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
            )
            await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(handle, host=args.host, port=args.port)
    print(f"browser-goat API listening on http://{args.host}:{args.port}", file=sys.stderr)
    async with server:
        await server.serve_forever()


_PID_FILE = Path.home() / ".browser-goat" / "server.pid"


def _get_pid() -> int | None:
    """Read the PID from the PID file, if it exists and is valid."""
    if not _PID_FILE.exists():
        return None
    try:
        raw = _PID_FILE.read_text().strip()
        return int(raw)
    except (ValueError, OSError):
        return None


def _remove_pid_file() -> None:
    """Remove the PID file if it exists."""
    with contextlib.suppress(OSError):
        _PID_FILE.unlink(missing_ok=True)


async def cmd_service_status(args: argparse.Namespace) -> None:
    """Check if both the browser-goat API and SearXNG are healthy."""
    browser_ok = False
    searxng_ok = False

    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
        try:
            resp = await client.get("http://localhost:8000/health")
            if resp.status_code == 200 and resp.json() == {"status": "ok"}:
                browser_ok = True
        except Exception:
            pass

        try:
            resp = await client.get(f"{args.searxng_url.rstrip('/')}/health")
            if resp.status_code == 200:
                searxng_ok = True
        except Exception:
            pass

    print("browser-goat API:", "healthy" if browser_ok else "unreachable")
    print("SearXNG:", "healthy" if searxng_ok else "unreachable")

    if browser_ok and searxng_ok:
        sys.exit(0)
    else:
        sys.exit(1)


async def cmd_service_start(args: argparse.Namespace) -> None:
    """Start the browser-goat HTTP API server as a background process."""
    _PID_FILE.parent.mkdir(parents=True, exist_ok=True)

    if sys.platform == "win32":
        creationflags = 0x00000008  # DETACHED_PROCESS
        popen_kwargs: dict[str, Any] = {"creationflags": creationflags}
    else:
        popen_kwargs = {"start_new_session": True}

    cmdline = [
        sys.executable,
        "-m",
        "browser_goat.cli",
        "serve",
        "--port", str(args.port),
        "--searxng-url", args.searxng_url,
    ]

    proc = subprocess.Popen(cmdline, **popen_kwargs)
    _PID_FILE.write_text(str(proc.pid))

    print(f"browser-goat service started (PID: {proc.pid})")

    # Wait up to 5 seconds for the health check to pass
    deadline = time.monotonic() + 5.0
    async with httpx.AsyncClient(timeout=httpx.Timeout(2.0)) as client:
        while time.monotonic() < deadline:
            try:
                resp = await client.get(f"http://localhost:{args.port}/health")
                if resp.status_code == 200 and resp.json() == {"status": "ok"}:
                    return
            except Exception:
                pass
            await asyncio.sleep(0.5)

    print("Warning: health check timed out — service may still be starting", file=sys.stderr)


async def cmd_service_stop(args: argparse.Namespace) -> None:
    """Stop the background browser-goat service."""
    _ = args.searxng_url  # accepted for CLI consistency but unused for stop

    pid = _get_pid()
    if pid is None:
        print("browser-goat service is not running (no PID file)", file=sys.stderr)
        sys.exit(1)

    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                capture_output=True,
                timeout=10,
            )
        else:
            os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        print(f"No process found with PID {pid}", file=sys.stderr)
    except Exception as e:
        print(f"Failed to stop process {pid}: {e}", file=sys.stderr)
        sys.exit(1)

    _remove_pid_file()
    print("browser-goat service stopped")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.guide:
        print(GUIDE_TEXT)
        return

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        if args.command == "search":
            asyncio.run(cmd_search(args))
        elif args.command == "extract":
            asyncio.run(cmd_extract(args))
        elif args.command == "verify":
            asyncio.run(cmd_verify(args))
        elif args.command == "serve":
            asyncio.run(cmd_serve(args))
        elif args.command == "service":
            if args.svc_command == "status":
                asyncio.run(cmd_service_status(args))
            elif args.svc_command == "start":
                asyncio.run(cmd_service_start(args))
            elif args.svc_command == "stop":
                asyncio.run(cmd_service_stop(args))
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
