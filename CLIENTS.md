# MCP client setup

browser-goat exposes `search`, `extract`, and `verify` over MCP stdio. For tool
inputs, results, and fallback behavior, use the [MCP reference](docs/mcp.md).
For launcher snippets, use the [distribution examples](distribution/README.md).

## Run a source checkout

Install Python 3.13+ and uv, then prepare the checkout using the
[installation guide](docs/install.md). Configure the client to launch:

```bash
uv run --project /path/to/browser-goat browser-goat-mcp --searxng-url http://localhost:8082
```

Replace `/path/to/browser-goat` with the absolute checkout path. Search and
verification require a SearXNG instance with JSON search enabled. Extracting a
known URL does not require SearXNG.

Client configuration schemas differ. Use the client's expected command,
argument, and environment fields; a generic `mcpServers` example is not a
universal configuration file. No client configuration is installed automatically.

## Other launch methods

For an available published Python package, select the MCP executable with
`uvx --from browser-goat browser-goat-mcp`. That command does not automatically
use changes in a local checkout.

The npm launcher also requires Node.js and a Python interpreter containing the
backend. It does not install Python or the Python package. See
[npm prerequisites](npm/README.md) for `PYTHON_CMD` and local-launch instructions.

## Check the right service

Compose publishes SearXNG on loopback port 8082 and the separate HTTP JSON API
on port 8003. The API is not an MCP endpoint. An MCP handshake proves that the
stdio server responds, not that SearXNG or a browser fetch tier is ready.
See [local deployment](docs/deployment.md) for independent startup checks.
