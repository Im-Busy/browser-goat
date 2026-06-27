"""MCP (Model Context Protocol) server for browser-goat.

Exposes search and extract as MCP tools for AI agent consumption via stdio transport.

Usage:
    browser-goat-mcp --searxng-url http://localhost:8080
    uvx browser-goat-mcp --searxng-url http://localhost:8080

Connecting (example MCP client config):
    {
        "mcpServers": {
            "browser-goat": {
                "command": "browser-goat-mcp",
                "args": ["--searxng-url", "http://localhost:8080"]
            }
        }
    }
"""

from __future__ import annotations

import argparse
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP

from browser_goat.router import BrowserGoat

# ── Global instance (set once at startup) ──────────────────────────────────
_meta: BrowserGoat | None = None


def get_meta() -> BrowserGoat:
    """Return the singleton BrowserGoat instance."""
    global _meta
    assert _meta is not None, "BrowserGoat not initialized. Call create_mcp_server() first."
    return _meta


def create_mcp_server(searxng_url: str) -> FastMCP:
    """Create and configure the FastMCP server with search and extract tools.

    Args:
        searxng_url: URL of the SearXNG instance.

    Returns:
        A configured FastMCP instance ready to run.
    """
    global _meta
    _meta = BrowserGoat(searxng_url=searxng_url)

    mcp = FastMCP("browser-goat")

    @mcp.tool()
    async def search(
        query: str,
        time_range: str | None = None,
        max_sources: int = 15,
        reliability_mode: Annotated[
            str, "Reliability level: 'standard', 'high', or 'maximum'."
        ] = "standard",
        strategy: Annotated[
            str, "Search strategy: 'auto', 'direct', or 'explore'."
        ] = "auto",
    ) -> dict[str, Any]:
        """Execute a full search pipeline: pre-search → SearXNG → post-search → extraction → reliability.

        Args:
            query: The search query string.
            time_range: Optional time filter — one of "day", "week", "month", "year".
            max_sources: Maximum number of sources to extract (default: 15, max: 50).
            reliability_mode: Reliability level — "standard", "high", or "maximum".
            strategy: Search strategy — "auto", "direct", or "explore".
        """
        meta = get_meta()
        max_sources = min(max(1, max_sources), 50)  # clamp to [1, 50]
        result = await meta.search(
            query=query,
            time_range=time_range,
            max_sources=max_sources,
            reliability_mode=reliability_mode,
            strategy=strategy,
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

    @mcp.tool()
    async def verify(
        query: str,
        rollouts: Annotated[int, "Number of parallel search rollouts (3-8)."] = 5,
        searxng_url: str = "",
    ) -> dict[str, Any]:
        """Run multi-rollout verification with consensus voting across parallel searches.

        Higher rollouts increase confidence through cross-verification. Each rollout
        independently searches and extracts; the final answer is determined by
        consensus voting with LLM tie-breaking when needed.

        Args:
            query: The search query string.
            rollouts: Number of parallel search rollouts (3-8, default: 5).
            searxng_url: Optional SearXNG URL override (uses default when empty).
        """
        meta = get_meta()
        rollouts = max(3, min(8, rollouts))
        reliability_mode = "high" if rollouts <= 5 else "maximum"
        result = await meta.search(query=query, reliability_mode=reliability_mode)
        return result.model_dump()

    return mcp


def main() -> None:
    """CLI entry point for the MCP server.

    Parses --searxng-url and runs the MCP stdio server.
    Registered in pyproject.toml as: browser-goat-mcp
    """
    parser = argparse.ArgumentParser(
        prog="browser-goat-mcp",
        description="MCP server for browser-goat — meta-layer search intelligence wrapping SearXNG",
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
