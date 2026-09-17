# MCP launch examples

browser-goat exposes `search`, `extract`, and `verify` over MCP stdio. SearXNG
must be available with JSON search enabled for search and verification. The
bundled HTTP API is separate from MCP.

## Launch from a checkout

Install Python 3.13+ and uv, then run from the checkout root:

```bash
uv sync --locked
docker compose up -d redis searxng
uv run browser-goat-mcp --searxng-url http://localhost:8082
```

For a client that starts the server from another working directory, use an
absolute checkout path:

```bash
uv run --project /path/to/browser-goat browser-goat-mcp --searxng-url http://localhost:8082
```

The client communicates with the process through stdin and stdout. It does not
connect to the Compose HTTP API at port 8003.

## Package launchers

These forms require the corresponding package to be available from its registry;
they do not automatically use repairs in a local checkout:

```bash
uvx --from browser-goat browser-goat-mcp
npx browser-goat
```

`browser-goat-mcp` is an executable in the `browser-goat` Python package, not a
separate package name. The npm launcher also requires Node.js and an existing
Python installation containing browser-goat. It does not install the Python
backend. Set `PYTHON_CMD` to that interpreter; see [npm setup](../npm/README.md).

## Example files

The JSON files below use the generic `mcpServers` format. Their directory names
are labels, not a compatibility guarantee for current client versions. Adapt
the command, arguments, environment, and outer schema to your client's local
documentation. In particular, do not paste these files unchanged into an
OpenCode configuration, and do not put executable configuration in a Copilot
instructions Markdown file.

| File | Launcher |
|---|---|
| [Desktop example](claude-desktop/mcp-config.json) | npm wrapper |
| [Cursor example](cursor/mcp-config.json) | npm wrapper |
| [Copilot example](copilot/mcp-config.json) | npm wrapper |
| [Windsurf example](windsurf/mcp-config.json) | npm wrapper |
| [OpenCode-labeled example](opencode/mcp-config.json) | Python package; outer schema needs adaptation |
| [Local example](mcp-configs/local.json) | Python package with explicit SearXNG URL |
| [Local Docker-backend example](mcp-configs/local-docker.json) | Host Python process using the Compose SearXNG port |

The local Docker-backend example does not start containers or connect to an MCP
HTTP endpoint. Start the backend separately. Set `SEARXNG_URL` or pass
`--searxng-url` if SearXNG is not at `http://localhost:8082`.

See [MCP integration](../docs/mcp.md) for input bounds, output fields, and
fallback behavior, and [local deployment](../docs/deployment.md) for startup
checks. Browser fetching is best-effort; answer agreement is not proof of truth.
