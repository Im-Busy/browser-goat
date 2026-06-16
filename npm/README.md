# browser-goat — MCP Server

MCP (Model Context Protocol) server for [browser-goat](https://github.com/Im-Busy/browser-goat), a meta-layer search intelligence wrapper for SearXNG.

This npm package is a **thin bridge** — it spawns the Python `browser-goat-mcp` backend and proxies MCP stdio communication. All search logic lives in the Python package.

## Prerequisites

- **Python 3.13+** — required
- **browser-goat** installed via pip/uv:
  ```bash
  pip install browser-goat
  # or
  uv add browser-goat
  ```
- **SearXNG** running somewhere (default: `http://localhost:8080`)

## Usage

### Direct (npx)

```bash
npx browser-goat
```

### MCP Client Config

Add to your MCP client configuration:

```json
{
  "mcpServers": {
    "browser-goat": {
      "command": "npx",
      "args": ["browser-goat"],
      "env": {
        "SEARXNG_URL": "http://localhost:8080"
      }
    }
  }
}
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SEARXNG_URL` | `http://localhost:8080` | SearXNG instance URL |
| `PYTHON_CMD` | `python` | Python interpreter command |

## MCP Tools

| Tool | Description |
|------|-------------|
| `search` | Execute a full search pipeline: pre-search → SearXNG → ranking → extraction |
| `extract` | Fetch and extract content from a single URL |

## License

MIT
