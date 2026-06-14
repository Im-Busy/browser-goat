"""MCP (Model Context Protocol) server for browsing-meta.

Exposes search and extract as MCP tools for AI agent consumption via stdio transport.

Usage:
    browsing-meta-mcp --searxng-url http://localhost:8080
    uvx browsing-meta-mcp --searxng-url http://localhost:8080

Connecting (example MCP client config):
    {
        "mcpServers": {
            "browsing-meta": {
                "command": "browsing-meta-mcp",
                "args": ["--searxng-url", "http://localhost:8080"]
            }
        }
    }
"""

from __future__ import annotations

import argparse
from typing import Any

from mcp.server.fastmcp import FastMCP

from browsing_meta.router import BrowsingMeta

# ── Global instance (set once at startup) ──────────────────────────────────
_meta: BrowsingMeta | None = None


def get_meta() -> BrowsingMeta:
    """Return the singleton BrowsingMeta instance."""
    global _meta
    assert _meta is not None, "BrowsingMeta not initialized. Call create_mcp_server() first."
    return _meta


def create_mcp_server(searxng_url: str) -> FastMCP:
    """Create and configure the FastMCP server with search and extract tools.

    Args:
        searxng_url: URL of the SearXNG instance.

    Returns:
        A configured FastMCP instance ready to run.
    """
    global _meta
    _meta = BrowsingMeta(searxng_url=searxng_url)

    mcp = FastMCP("browsing-meta")

    @mcp.tool()
    async def search(
        query: str,
        time_range: str | None = None,
        max_sources: int = 15,
    ) -> dict[str, Any]:
        """Execute a full search pipeline: pre-search → SearXNG → post-search → extraction → reliability.

        Args:
            query: The search query string.
            time_range: Optional time filter — one of "day", "week", "month", "year".
            max_sources: Maximum number of sources to extract (default: 15, max: 50).
        """
        meta = get_meta()
        max_sources = min(max(1, max_sources), 50)  # clamp to [1, 50]
        result = await meta.search(
            query=query,
            time_range=time_range,
            max_sources=max_sources,
            strategy="auto",
        )
        return result.model_dump()

    @mcp.tool()
    async def extract(url: str) -> dict[str, Any]:
        """Fetch and extract content from a single URL using the 7-tier cascading extractor.

        Args:
            url: The full URL (http:// or https://) to extract content from.
        """
        meta = get_meta()
        fetcher = meta.scrapling
        extractor = meta.content_extractor
        profile = meta.browser_profiles.get_random_profile()

        fetch_result = await fetcher.fetch(url, browser_profile=profile)
        if not fetch_result.success:
            return {
                "url": url,
                "error": fetch_result.error or "fetch failed",
                "success": False,
            }

        content = extractor.extract(fetch_result.html, url)
        return {
            "url": url,
            "title": content.title,
            "text": content.text,
            "extraction_tier": content.extraction_tier,
            "text_length": len(content.text),
            "success": True,
        }

    return mcp


def main() -> None:
    """CLI entry point for the MCP server.

    Parses --searxng-url and runs the MCP stdio server.
    Registered in pyproject.toml as: browsing-meta-mcp
    """
    parser = argparse.ArgumentParser(
        prog="browsing-meta-mcp",
        description="MCP server for browsing-meta — meta-layer search intelligence wrapping SearXNG",
    )
    parser.add_argument(
        "--searxng-url",
        default="http://localhost:8080",
        help="SearXNG instance URL (default: http://localhost:8080)",
    )
    args = parser.parse_args()

    mcp = create_mcp_server(searxng_url=args.searxng_url)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
