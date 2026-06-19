# browser-goat Documentation

Production-grade web search for AI agents. browser-goat wraps SearXNG with six processing stages — intent detection, hybrid ranking, anti-bot extraction, quality gating, adaptive strategy, and consensus verification — giving you agent-ready search results on your own infrastructure.

## Getting Started

New to browser-goat? Start here:

- **[Installation](install.md)** — pip, uv, or Docker. Get up and running in under a minute.
- **[Quickstart](quickstart.md)** — Your first search, extraction, and MCP connection in 5 minutes.

## Guides

- **[CLI Reference](cli.md)** — Every command and flag: `search`, `extract`, `verify`, `serve`, `mcp`.
- **[Python Library](library.md)** — Use browser-goat as a library. Full API reference for the `BrowserGoat` class.
- **[MCP Integration](mcp.md)** — Connect browser-goat to Claude Desktop, Cursor, OpenCode, and other AI coding tools.
- **[Configuration](configuration.md)** — Environment variables, engine selection, language settings, and browser profiles.
- **[Docker](docker.md)** — Deploy SearXNG + browser-goat with `docker compose up`.

## Reference

- **[Architecture](architecture.md)** — How the six-stage pipeline works, from query to answer.
- **[GitHub Repository](https://github.com/Im-Busy/browser-goat)** — Source code, issues, and contributing.

## Quick Install

```bash
pip install browser-goat
# or
uv add browser-goat
```

Then make sure SearXNG is running at `http://localhost:8080`.
