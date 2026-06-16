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
import json
import sys
from typing import Any

from browser_goat.router import BrowserGoat


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="browser-goat",
        description="Meta-layer search intelligence wrapping SearXNG",
    )
    sub = parser.add_subparsers(dest="command", required=True)

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


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "search":
            asyncio.run(cmd_search(args))
        elif args.command == "extract":
            asyncio.run(cmd_extract(args))
        elif args.command == "verify":
            asyncio.run(cmd_verify(args))
        elif args.command == "serve":
            asyncio.run(cmd_serve(args))
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
