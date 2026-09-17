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
uvx --from browser-goat browser-goat-mcp --searxng-url http://localhost:8082
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
| `--searxng-url` | `str` | `http://localhost:8082` | — | SearXNG instance URL |
| `--engines` | `str` (space-separated) | `None` (language-based) | — | SearXNG engines to use, e.g. `google bing scholar` |
| `--time-range` | `str` | `None` | `day`, `week`, `month`, `year` | Time filter for results |
| `--language` | `str` | `auto` | — | Detect language; explicit codes override detection |
| `--max-sources` | `int` | `15` | 1-50 | Maximum source pages per pass/rollout |
| `--strategy` | `str` | `default` | `default`, `direct`, `auto`, `explore`, `decompose` | Search strategy |
| `--reliability` | `str` | `standard` | `standard`, `high`, `maximum`, `auto` | Reliability mode |
| `--format` | `str` | `json` | `json`, `pretty` | Output format |
| `--llm` | `str` | none | provider:model | Explicitly configure verification tie-breaking |

### Strategy Modes

| Value | Behavior |
|-------|----------|
| `default` | Standard single-pass search with ranking and extraction |
| `auto` | Query analysis determines the best strategy automatically |
| `explore` | Adaptive exploration with multi-angle candidate queries |
| `decompose` | Requires a library `llm_call`; CLI falls back to default search |
| `direct` | Alias for default |

### Reliability Modes

| Value | Behavior |
|-------|----------|
| `standard` | Single attempt with basic quality checks |
| `high` | Up to five rollouts; consensus voting or plurality fallback |
| `maximum` | Up to eight rollouts; optional LLM tie-breaking for ties |
| `auto` | High for complex research/comparison, otherwise standard |

Quality checks report whether the answer passed; they do not retry synthesis.
Without a configured LLM, ties are reported as `fallback`. Consensus describes
agreement, not independently established truth.

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
| `--searxng-url` | `str` | `http://localhost:8082` | — | SearXNG instance URL |
| `--format` | `str` | `json` | `json`, `pretty` | Output format |

### Output Fields

| Field | Type | Description |
|-------|------|-------------|
| `url` | `str` | The extracted URL |
| `title` | `str` | Page title |
| `text` | `str` | Full clean extracted text |
| `extraction_tier` | `int` | Which tier of the cascading extractor succeeded |
| `text_length` | `int` | Total length of extracted text in characters |
| `success` | `bool` | False on fetch failure or empty extracted text |
| `error` | `str` or `null` | Failure description |

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
| `--searxng-url` | `str` | `http://localhost:8082` | — | SearXNG instance URL |
| `--rollouts` | `int` | `5` | 3-8 | Requested parallel search rollouts |
| `--format` | `str` | `json` | `json`, `pretty` | Output format |

The exact requested count is honored unless four matching answers stop pending
work. `rollouts_run` and `verification.rollout_count` report actual completions.
The result includes `vote_counts` and `candidates`. More than five rollouts
permit the optional LLM tie-breaker; no LLM means a labeled fallback.

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
| `--host` | `str` | `127.0.0.1` | Host to bind to; non-loopback binding requires explicit opt-in |
| `--port` | `int` | `8000` | Port to listen on |
| `--searxng-url` | `str` | `http://localhost:8082` | SearXNG instance URL |

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
| `engines` | list of strings or `null` | `null` | Search engine selection |
| `language` | `str` | `auto` | Language override |
| `time_range` | `str` or `null` | `null` | Time filter |
| `max_sources` | `int` | `15` | Maximum source pages |
| `strategy` | `str` | `"default"` | Search strategy |
| `reliability` | `str` | `"standard"` | Reliability mode |

`reliability_mode` is also accepted; it takes precedence over `reliability`.
The API returns JSON errors: `400` for invalid JSON/options, `408` for a
request-body timeout, `413` for bodies larger than 64 KiB, and `502` for
SearXNG transport errors. Send a `Content-Length` header; chunked request
bodies are not supported. `/health` checks listener liveness, not backend health.
The API has no authentication. Native `serve` and `service start` bind to
`127.0.0.1`. The Docker command explicitly binds `0.0.0.0` inside the container;
Compose keeps its host port on loopback. Non-loopback native binding requires
an explicit `--host` and a trusted access policy or reverse proxy.

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

Starts the MCP stdio server for AI agent consumption. Exposes `search`, `extract`, and `verify`.

```
browser-goat-mcp [OPTIONS]
```

### Flags

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--searxng-url` | `str` | `http://localhost:8082` | SearXNG instance URL |

### MCP Tools

| Tool | Description |
|------|-------------|
| `search` | Full pipeline with query, time_range, and max_sources parameters |
| `extract` | Fetch and extract a single URL with anti-bot bypass |
| `verify` | Request 3-8 rollouts and return vote and fallback metadata |

### MCP Client Configuration

```json
{
  "mcpServers": {
    "browser-goat": {
      "command": "browser-goat-mcp",
      "args": ["--searxng-url", "http://localhost:8082"]
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
      "args": ["--from", "browser-goat", "browser-goat-mcp", "--searxng-url", "http://localhost:8082"]
    }
  }
}
```

With `npx` (requires Python with browser-goat installed; `PYTHON_CMD` selects the interpreter):

```json
{
  "mcpServers": {
    "browser-goat": {
      "command": "npx",
      "args": ["browser-goat"],
      "env": { "SEARXNG_URL": "http://localhost:8082" }
    }
  }
}
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SEARXNG_URL` | `http://localhost:8082` | SearXNG instance URL (used by the npx MCP wrapper) |

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
| `2` | Argument parser rejected a flag or value |

Search/extract/verify execution errors write JSON to stderr. Argument-parser
errors and service lifecycle messages use human-readable text:

```json
{"error": "connection refused"}
```

## Background service helpers

```bash
browser-goat service start --port 8000
browser-goat service status --port 8000
browser-goat service stop
```

These manage a PID file under `~/.browser-goat`; they do not start SearXNG or
the MCP server. The background child explicitly binds to `127.0.0.1`.
`status --port 8003` checks the Compose API instead. Use an
existing supervisor rather than starting duplicate listeners. `--version` and
`--guide` are top-level informational flags.
