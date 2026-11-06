# browser-goat — MCP Server

Node.js launcher for the Python MCP (Model Context Protocol) stdio server in
[browser-goat](https://github.com/Im-Busy/browser-goat), a SearXNG search,
ranking, and page-extraction pipeline with optional answer voting.

This npm package is a **thin bridge** — it spawns the Python `browser-goat-mcp` backend and proxies MCP stdio communication. All search logic lives in the Python package.

## Prerequisites

- **Python 3.13+** — required
- **browser-goat** installed via pip/uv:
  ```bash
  pip install browser-goat
  # or
  uv add browser-goat
  ```
- **SearXNG** running somewhere (default: `http://localhost:8082`)

Package-index commands require published packages. To use the Python code from
a checkout, run `uv sync --locked` at its root and set `PYTHON_CMD` to that
checkout's virtual-environment interpreter. Installing with `uv add` does not
make the package available to an unrelated system `python`.

## Usage

### Direct (npx)

```bash
npx browser-goat
```

To use the launcher from the checkout instead of downloading it from npm, run
`node npm/index.js` at the checkout root with the same `PYTHON_CMD` setting.
The selected Python interpreter must contain the backend you intend to run.

### MCP Client Config

Add to your MCP client configuration:

```json
{
  "mcpServers": {
    "browser-goat": {
      "command": "npx",
      "args": ["browser-goat"],
      "env": {
        "SEARXNG_URL": "http://localhost:8082"
      }
    }
  }
}
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SEARXNG_URL` | `http://localhost:8082` | SearXNG instance URL |
| `PYTHON_CMD` | `python` | Python interpreter command |

`PYTHON_CMD` must be one executable path, not a shell command such as
`uv run python`. For a source checkout on Windows, point it to
`C:\path\to\browser-goat\.venv\Scripts\python.exe`. The interpreter must have
the Python package installed. Arguments after `npx browser-goat` are forwarded
to the backend, so `npx browser-goat --searxng-url http://localhost:8082` works.

The wrapper inherits stdio without buffering MCP messages, forwards SIGINT and
SIGTERM, and preserves backend failures as nonzero exit codes.

## MCP Tools

| Tool | Description |
|------|-------------|
| `search` | Full search pipeline: pre-search → SearXNG → ranking → extraction → reliability. Use `reliability_mode` for verification (`"high"` or `"maximum"`) |
| `extract` | Fetch and extract content from a single URL |
| `verify` | Request 3-8 rollouts, return actual completions and votes; LLM tie-breaking is optional |

See the [MCP reference](https://github.com/Im-Busy/browser-goat/blob/public/docs/mcp.md)
for input bounds and fallback semantics. Agreement is not proof of correctness.

## License

MIT
