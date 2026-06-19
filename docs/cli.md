# CLI Reference

## Entry Points

Two commands are installed when you install the package:

| Command | Entry Point | Purpose |
|---------|-------------|---------|
| `browser-goat` | `browser_goat.cli:main` | Full CLI with search, extract, verify, and serve subcommands |
| `browser-goat-mcp` | `browser_goat.mcp_server:main` | MCP stdio server for AI agent consumption |

Both can run via `uvx` for zero-install usage:

```bash
uvx browser-goat search "your query"
uvx browser-goat-mcp --searxng-url http://localhost:8080
```

---

## `browser-goat search`

Runs the full search pipeline: query intent detection, SearXNG dispatch, result ranking, content extraction, and reliability gating.

```
browser-goat search QUERY [OPTIONS]
```

### Positional Arguments

| Argument | Type | Description |
|----------|------|-------------|
| `QUERY` | `str` | Search query string |

### Flags

| Flag | Type | Default | Choices | Description |
|------|------|---------|---------|-------------|
| `--searxng-url` | `str` | `http://localhost:8080` | — | SearXNG instance URL |
| `--engines` | `str` (space-separated) | `None` (all engines) | — | SearXNG engines to use, e.g. `google bing scholar` |
| `--time-range` | `str` | `None` | `day`, `week`, `month`, `year` | Time filter for results |
| `--language` | `str` | `en` | — | Language code for results |
| `--max-sources` | `int` | `15` | — | Maximum source pages to extract |
| `--strategy` | `str` | `default` | `default`, `auto`, `explore`, `decompose` | Search strategy |
| `--reliability` | `str` | `standard` | `standard`, `high`, `maximum` | Reliability mode |
| `--format` | `str` | `json` | `json`, `pretty` | Output format |

### Strategy Modes

| Value | Behavior |
|-------|----------|
| `default` | Standard single-pass search with ranking and extraction |
| `auto` | Query analysis determines the best strategy automatically |
| `explore` | Adaptive exploration with multi-angle candidate queries |
| `decompose` | Breaks complex queries into subtasks, solves recursively |

### Reliability Modes

| Value | Behavior |
|-------|----------|
| `standard` | Single attempt with basic quality checks |
| `high` | Retries on insufficient results, forces answer on repeated failure |
| `maximum` | Multi-rollout consensus voting with LLM tie-breaking |

### Examples

```bash
browser-goat search "latest machine learning research" --time-range week --max-sources 5

browser-goat search "Python vs Rust performance" --strategy explore --reliability high

browser-goat search "quantum computing breakthroughs" --engines google scholar --language en

browser-goat search "climate change" --searxng-url http://my-searxng:8080 --format pretty
```

---

## `browser-goat extract`

Fetches a single URL and extracts content using the cascading extractor with anti-bot bypass.

```
browser-goat extract URL [OPTIONS]
```

### Positional Arguments

| Argument | Type | Description |
|----------|------|-------------|
| `URL` | `str` | URL to extract content from |

### Flags

| Flag | Type | Default | Choices | Description |
|------|------|---------|---------|-------------|
| `--searxng-url` | `str` | `http://localhost:8080` | — | SearXNG instance URL |
| `--format` | `str` | `json` | `json`, `pretty` | Output format |

### Output Fields

| Field | Type | Description |
|-------|------|-------------|
| `url` | `str` | The extracted URL |
| `title` | `str` | Page title |
| `text` | `str` | Clean extracted text (truncated to 1,000 characters in output) |
| `extraction_tier` | `str` | Which tier of the cascading extractor succeeded |
| `text_length` | `int` | Total length of extracted text in characters |

### Examples

```bash
browser-goat extract "https://example.com/article"

browser-goat extract "https://example.com" --format pretty

browser-goat extract "https://example.com" --searxng-url http://my-searxng:8080
```

---

## `browser-goat verify`

Runs multi-rollout verification on a query. Launches multiple parallel searches and votes on the consensus answer.

```
browser-goat verify QUERY [OPTIONS]
```

### Positional Arguments

| Argument | Type | Description |
|----------|------|-------------|
| `QUERY` | `str` | Query to verify |

### Flags

| Flag | Type | Default | Choices | Description |
|------|------|---------|---------|-------------|
| `--searxng-url` | `str` | `http://localhost:8080` | — | SearXNG instance URL |
| `--rollouts` | `int` | `5` | — | Number of parallel search rollouts |
| `--format` | `str` | `json` | `json`, `pretty` | Output format |

Reliability mode is derived from rollout count: `high` for 5 or fewer rollouts, `maximum` for more than 5.

### Examples

```bash
browser-goat verify "what is the capital of France"

browser-goat verify "latest AI safety research" --rollouts 7 --format pretty
```

---

## `browser-goat serve`

Starts an HTTP JSON API server. Accepts search requests at `POST /search` and returns health status at `GET /health` and `GET /`.

```
browser-goat serve [OPTIONS]
```

### Flags

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--host` | `str` | `0.0.0.0` | Host to bind to |
| `--port` | `int` | `8000` | Port to listen on |
| `--searxng-url` | `str` | `http://localhost:8080` | SearXNG instance URL |

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check, returns `{"status":"ok"}` |
| `GET` | `/` | Health check, returns `{"status":"ok"}` |
| `POST` | `/search` | Execute a search pipeline |

The `POST /search` endpoint accepts a JSON body with these fields:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `query` | `str` | (required) | Search query |
| `time_range` | `str` or `null` | `null` | Time filter |
| `max_sources` | `int` | `15` | Maximum source pages |
| `strategy` | `str` | `"default"` | Search strategy |
| `reliability` | `str` | `"standard"` | Reliability mode |

### Examples

```bash
browser-goat serve

browser-goat serve --port 9090 --host 127.0.0.1

browser-goat serve --searxng-url http://my-searxng:8080
```

```bash
# Health check
curl http://localhost:8000/health

# Search
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "latest AI research", "max_sources": 10}'
```

---

## `browser-goat-mcp`

Starts the MCP stdio server for AI agent consumption. Exposes `search` and `extract` tools over the Model Context Protocol.

```
browser-goat-mcp [OPTIONS]
```

### Flags

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--searxng-url` | `str` | `http://localhost:8080` | SearXNG instance URL |

### MCP Tools

| Tool | Description |
|------|-------------|
| `search` | Full pipeline with query, time_range, and max_sources parameters |
| `extract` | Fetch and extract a single URL with anti-bot bypass |

### MCP Client Configuration

```json
{
  "mcpServers": {
    "browser-goat": {
      "command": "browser-goat-mcp",
      "args": ["--searxng-url", "http://localhost:8080"]
    }
  }
}
```

With `uvx`:

```json
{
  "mcpServers": {
    "browser-goat": {
      "command": "uvx",
      "args": ["browser-goat-mcp", "--searxng-url", "http://localhost:8080"]
    }
  }
}
```

With `npx` (npm wrapper starts the Python backend as a subprocess):

```json
{
  "mcpServers": {
    "browser-goat": {
      "command": "npx",
      "args": ["browser-goat"],
      "env": { "SEARXNG_URL": "http://localhost:8080" }
    }
  }
}
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SEARXNG_URL` | `http://localhost:8080` | SearXNG instance URL (used by the npx MCP wrapper) |

The `--searxng-url` flag on all CLI commands sets the same value directly and takes precedence over the environment variable.

---

## Output Formats

### `--format json`

Compact JSON output on one line. Default for all commands.

```bash
browser-goat search "Python" --format json
```

### `--format pretty`

Indented JSON with two-space indentation, suitable for human reading.

```bash
browser-goat search "Python" --format pretty
```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | Error — connection failure, invalid input, SearXNG error, or fetch failure |

All commands write errors to stderr in JSON format with an `error` field:

```json
{"error": "connection refused"}
```
