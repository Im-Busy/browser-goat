# browser-goat Documentation

browser-goat wraps SearXNG with query analysis, ranking, page extraction,
quality checks, optional strategy routing, and agreement-based verification.
Browser-backed recovery and LLM stages have separate setup requirements.

## Getting Started

New to browser-goat? Start here:

- **[Installation](install.md)** — Python packages and browser dependencies.
- **[Quickstart](quickstart.md)** — First search, extraction, and MCP connection.

## Guides

- **[CLI Reference](cli.md)** — `search`, `extract`, `verify`, `serve`, `service`, and the separate MCP entry point.
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

Then make sure SearXNG is running at `http://localhost:8082`.
