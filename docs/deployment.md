# Local deployment

Run browser-goat from a source checkout as an HTTP JSON API, or launch its MCP
stdio server from an MCP client. SearXNG must support JSON search for search and
verification. Extracting a known URL does not require SearXNG.

These instructions use files included in the checkout. They do not require
machine-specific setup scripts, scheduled tasks, or user-level environment changes.

## Choose a deployment

| Use case | Start here |
|---|---|
| HTTP API with a bundled search backend | [Compose stack](#compose-stack) |
| Python process with a bundled or existing SearXNG instance | [Native HTTP API](#native-http-api) |
| Tools launched by an MCP client | [MCP stdio](#mcp-stdio) |

The HTTP API is not MCP. Starting the API does not register tools with an MCP
client, and a successful MCP handshake does not prove SearXNG is reachable.

## Compose stack

Install Docker with the Compose plugin. Run the following commands from the
checkout root.

1. Build and start the services:

   ```bash
   docker compose up --build -d
   ```

   The [Compose file](../docker-compose.yml) starts Valkey (`redis`), SearXNG,
   and browser-goat. The [Dockerfile](../Dockerfile) installs the Python package,
   Chromium binaries, and browser system libraries. A build needs network access;
   startup time depends on image availability and service health.

2. Inspect service state and startup logs:

   ```bash
   docker compose ps
   docker compose logs --tail 100 browser-goat searxng
   ```

3. Check the API listener and SearXNG separately:

   ```bash
   curl --fail http://localhost:8003/health
   curl --fail http://localhost:8082/config
   ```

   In Windows PowerShell 5.1, use `curl.exe` rather than the `curl` alias.
   `/health` returns `{"status":"ok"}` when the API listener responds. Neither
   endpoint proves that external search engines or browser fetch tiers work.

The host endpoints are `http://localhost:8003` for the HTTP API and
`http://localhost:8082` for SearXNG. Both ports are bound to loopback. Inside the
Compose network, browser-goat connects to SearXNG at `http://searxng:8080`.

To stop the stack without deleting named volumes:

```bash
docker compose down
```

Services use Docker's `unless-stopped` restart policy. Docker must itself be
running; this policy does not install a host startup service. See
[Docker deployment](docker.md) for configuration and persistent volumes.

## Native HTTP API

Install Python 3.13+ and uv. Run the following commands from the checkout root.

1. Install the locked dependencies:

   ```bash
   uv sync --locked
   ```

2. Start the bundled backend, unless a SearXNG instance is already available:

   ```bash
   docker compose up -d redis searxng
   ```

   The bundled [SearXNG settings](../docker/searxng/settings.yml) enable JSON
   search. An independently deployed instance must also include `json` in
   `search.formats`.

3. Start the API in the foreground:

   ```bash
   uv run browser-goat serve --host 127.0.0.1 --port 8000 --searxng-url http://localhost:8082
   ```

4. In another terminal, check both services:

   ```bash
   uv run browser-goat service status --port 8000 --searxng-url http://localhost:8082
   ```

   This command exits nonzero if either health check fails. For a Compose API,
   use `--port 8003` instead. Stop the foreground API with Ctrl+C.

Install the browser binaries described in [installation](install.md) before
using browser-backed fetch tiers. A Python package install alone is not a
browser-readiness check.

For an optional background process, the CLI provides:

```bash
uv run browser-goat service start --port 8000 --searxng-url http://localhost:8082
uv run browser-goat service status --port 8000 --searxng-url http://localhost:8082
uv run browser-goat service stop
```

These commands manage the API process and a PID file under `~/.browser-goat/`.
They do not start SearXNG, install a Windows service, or configure restart at boot.
Do not run `service start` while a foreground API already occupies the same port.

## MCP stdio

After syncing a checkout, use this launch command in the MCP client. Replace
the path with the absolute path to the checkout:

```bash
uv run --project /path/to/browser-goat browser-goat-mcp --searxng-url http://localhost:8082
```

The MCP server exposes `search`, `extract`, and `verify`. It does not connect to
the HTTP API on port 8000 or 8003. See [MCP integration](mcp.md) for tool inputs
and [distribution examples](../distribution/README.md) for launch snippets.
Client configuration schemas differ; do not copy a wrapper key without checking
the client's expected format.

## Check a search

From a prepared checkout with SearXNG running:

```bash
uv run browser-goat search "Python asyncio documentation" --max-sources 1 --searxng-url http://localhost:8082
```

This makes external requests. Inspect `sources`, `extraction_success_rate`, and
`reliability` in the returned JSON. A running listener or a zero exit code alone
does not establish search quality or anti-bot compatibility.

## Troubleshooting and access control

| Symptom | Check |
|---|---|
| Address already in use | Identify the process using the chosen port. Stop only a process you own, or choose another API port with `--port`. |
| SearXNG unreachable | Inspect `docker compose ps`, service logs, and the configured SearXNG URL. |
| SearXNG search returns HTTP 403 | Confirm that `search.formats` includes `json`. |
| Browser executable missing | Install browser binaries and the platform libraries listed in [installation](install.md). |
| MCP starts but search fails | Check SearXNG independently; MCP startup does not probe search readiness. |

The HTTP API has no authentication. Keep loopback bindings unless a separate
authenticated access layer and network policy are in place. Set a non-default
SearXNG secret for deployments beyond a disposable local test. Do not commit
credentials. Browser escalation and answer agreement do not guarantee access
to a target site or factual correctness.
