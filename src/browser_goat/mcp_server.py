"""MCP stdio tools backed by the same library paths as the CLI and HTTP API."""

from __future__ import annotations

import argparse
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from browser_goat.router import BrowserGoat

_meta: BrowserGoat | None = None


def get_meta() -> BrowserGoat:
    """Return the most recently created server's instance (compatibility helper)."""
    assert _meta is not None, "Call create_mcp_server() first."
    return _meta


def create_mcp_server(searxng_url: str) -> FastMCP[Any]:
    """Create isolated search, extract, and verify tools with lifecycle cleanup."""
    global _meta
    meta = BrowserGoat(searxng_url=searxng_url)
    _meta = meta

    @asynccontextmanager
    async def lifespan(server: FastMCP[Any]) -> AsyncIterator[None]:
        try:
            yield None
        finally:
            await meta.close()

    mcp: FastMCP[Any] = FastMCP("browser-goat", lifespan=lifespan)
    annotations = ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                                  openWorldHint=True, idempotentHint=False)

    @mcp.tool(annotations=annotations)
    async def search(
        query: str,
        time_range: Literal["day", "week", "month", "year"] | None = None,
        max_sources: Annotated[int, Field(ge=1, le=50)] = 15,
        reliability_mode: Literal["standard", "high", "maximum", "auto"] = "standard",
        strategy: Literal["auto", "default", "direct", "explore", "decompose"] = "auto",
    ) -> dict[str, Any]:
        """Search SearXNG, rank and extract sources, and optionally vote across rollouts."""
        result = await meta.search(query=query, time_range=time_range, max_sources=max_sources,
                                   reliability_mode=reliability_mode, strategy=strategy)
        return result.model_dump(mode="json")

    @mcp.tool(annotations=annotations)
    async def extract(url: str) -> dict[str, Any]:
        """Fetch an HTTP(S) URL and return text from the seven-tier content extractor."""
        return await meta.extract(url)

    @mcp.tool(annotations=annotations)
    async def verify(
        query: str,
        rollouts: Annotated[int, Field(ge=3, le=8)] = 5,
        searxng_url: str = "",
    ) -> dict[str, Any]:
        """Run 3-8 rollouts; return vote counts, actual completions, and honest fallback metadata.

        Four matching answers establish consensus. A plurality below that threshold
        is returned without consensus. More than five rollouts permit an optional
        configured LLM tie-breaker; without one, the method remains 'fallback'.
        Collection has a 40-second budget and three sources per rollout. Unfinished
        work is cancelled and drained; partial/timeout metadata accompanies any
        completed answers. Cleanup can add latency beyond the collection budget.
        """
        if searxng_url:
            async with BrowserGoat(searxng_url=searxng_url) as override:
                return await override.verify(query, rollouts)
        return await meta.verify(query, rollouts)

    return mcp


def main() -> None:
    """Run the MCP stdio server. Diagnostics belong on stderr, not stdout."""
    parser = argparse.ArgumentParser(prog="browser-goat-mcp", description=__doc__)
    parser.add_argument("--searxng-url", default=os.environ.get("SEARXNG_URL", "http://localhost:8082"))
    args = parser.parse_args()
    create_mcp_server(args.searxng_url).run(transport="stdio")


if __name__ == "__main__":
    main()
