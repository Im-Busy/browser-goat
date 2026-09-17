# browser-goat

A Python search pipeline around SearXNG for AI agents and applications. It
classifies queries, ranks results, extracts page text, and optionally compares
answers across multiple searches. Available as a library, CLI, HTTP JSON API,
and MCP stdio server.

## Quick start

Requires Python 3.13+ and a SearXNG instance with JSON search enabled. From a
checkout, start the bundled search backend:

```bash
uv sync --locked
docker compose up -d redis searxng
uv run browser-goat search "Python asyncio documentation" --max-sources 2
uv run browser-goat extract "https://example.com"
```

SearXNG uses host port `8082`. The full Compose stack also exposes the HTTP
search API at `http://localhost:8003`. That API is **not an MCP endpoint**.

### MCP

For a client that accepts `mcpServers` configuration:

```json
{
  "mcpServers": {
    "browser-goat": {
      "command": "uvx",
      "args": ["--from", "browser-goat", "browser-goat-mcp"],
      "env": { "SEARXNG_URL": "http://localhost:8082" }
    }
  }
}
```

The npm wrapper is an alternative: `npx browser-goat`. It requires an existing
Python installation containing `browser-goat`; set `PYTHON_CMD` to that
interpreter's path. It does not install Python or the Python package.
See [MCP integration](docs/mcp.md) and [npm prerequisites](npm/README.md).

### Python library

```python
import asyncio
from browser_goat import BrowserGoat

async def main() -> None:
    async with BrowserGoat(searxng_url="http://localhost:8082") as goat:
        result = await goat.search("Python asyncio documentation", max_sources=2)
        print(result.answer)

asyncio.run(main())
```

## Behavior and limits

- `default` (alias `direct`) runs query analysis, SearXNG, URL cleanup,
  RRF/BM25+/MMR ranking, extraction, and quality checks.
- `explore` merges results from multiple query variants before ranking. Without
  an LLM, it uses the direct query and available rule-based synonyms.
- `decompose` uses an explicitly supplied library chat callback for recursive
  subtasks. Without that callback, it falls back to the default search path.
- `auto` chooses a strategy from query classification.
- `high` requests five rollouts; `maximum` requests eight. Four matching
  normalized answers can stop remaining work. A plurality is retained even
  without consensus. `verify --rollouts N` accepts 3-8, with actual completions
  reported in `rollouts_run`.
- Verification has a **40-second shared collection budget**, including any
  optional LLM tie-breaker. At the deadline, unfinished rollouts and their page
  fetches are cancelled and drained before returning completed results. Cleanup
  can add latency; this is not a hard 40-second transport guarantee.
  `verification` reports `timed_out`, `partial`, `stop_reason`,
  `requested_rollouts`, `failed_rollouts`, and `cancelled_rollouts`. No usable
  completions means `method="rollout_failure"` and `quality_passed=false`, not
  successful empty output.
- Standalone `verify` (library, CLI, MCP) requests **three sources per rollout**
  to avoid spending its whole deadline on low-ranked slow pages. `search` with
  high/maximum reliability retains the caller's `max_sources`; it uses the same
  collection deadline. One completed answer remains a non-consensus fallback.
- Verification measures agreement, **not factual truth**. Failed quality
  checks are excluded from voting. A single surviving answer is not consensus.
- No LLM is required. Ordinary answers list extracted source summaries.
  `BROWSER_GOAT_LLM` optionally configures verification tie-breaking; it does
  not enable decomposition or extraction enrichment. No configured LLM means
  tie-breaking is reported as `fallback`, not `llm`.
- Quality checks report failures; the basic pipeline does not synthesize or
  retry an answer. `force_answer_used` stays false when no synthesis ran.
- Search engines and target sites still impose limits. Browser-backed fetch
  tiers are best-effort, not a guarantee of access to every site.

## Extraction backends

Fetching tries HTTPX, Scrapling, Scrapling with challenge solving, Crawl4AI,
Playwright, then plain HTTPX. HTML-to-text extraction is a separate seven-tier
cascade.

HTTP 200 is not enough: blank pages, known challenge screens, and JavaScript-only
shells continue to the next tier and are not cached. Concurrent requests for
the same URL share an in-flight fetch. This heuristic does not recognize every
anti-bot page or establish topical relevance.

Install browser binaries for browser-backed fetch tiers:

```bash
uv run playwright install chromium
uv run patchright install chromium
```

Linux hosts also need browser system libraries (`playwright install --with-deps
chromium`). The Dockerfile installs these. Crawl4AI supports optional proxy
rotation through `CRAWL4AI_PROXY_LIST`; no proxy service is bundled.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `SEARXNG_URL` | `http://localhost:8082` | Search backend |
| `CONTENT_CACHE_TTL_SECONDS` | `900` | In-process HTML cache TTL; `0` disables reuse |
| `CONTENT_CACHE_MAX_ENTRIES` | `256` | LRU entry limit; `0` disables storage |
| `CRAWL4AI_PROXY_LIST` | empty | Comma-separated proxy URLs for the Crawl4AI tier |
| `BROWSER_GOAT_LLM` | empty | Optional verifier provider, such as `ollama:llama3` |
| `BROWSER_GOAT_OLLAMA_HOST` | `http://localhost:11434` | Ollama endpoint |
| `BROWSER_GOAT_OPENAI_API_KEY` | empty | Optional OpenAI verifier credential |

Native `serve` and `service start` bind to `127.0.0.1` by default. Docker's
explicit internal `0.0.0.0` binding remains behind a loopback Compose host port.
Do not expose the unauthenticated HTTP API to an untrusted network. See
[configuration](docs/configuration.md) and [Docker deployment](docs/docker.md).

## Development and verification

```bash
uv run pytest
uv run ruff check src/ tests/
uv run mypy src/
```

The default suite is offline: unit tests use mocks, full-path smoke tests use a
local SearXNG-shaped HTTP fixture, and load tests use a local fake server. LLM
providers are disabled in tests. These checks do not prove live engine or
anti-bot compatibility. Tests marked `integration` require explicit opt-in
(`uv run pytest --live -m integration`) and make external requests.

For a bounded local-interface smoke run:

```bash
uv run pytest tests/test_interfaces.py tests/test_repair_regressions.py
```

This exercises the library strategy/reliability matrix, CLI JSON and pretty
output, HTTP validation/errors, Python MCP stdio, and npm MCP stdio. Node.js is
required for the npm smoke test. Browser adapters use deterministic tests;
real browser binaries and external services require separate live validation.

After installing the declared dependencies and browser binaries, run
`uv run pytest tests/test_interfaces.py --browser-local -m browser_local` to
exercise Scrapling, Crawl4AI, and Playwright on local HTML. This does not test
external anti-bot challenge solving.

## Documentation

- [Installation](docs/install.md) and [quickstart](docs/quickstart.md)
- [CLI and HTTP API](docs/cli.md)
- [Python API](docs/library.md)
- [MCP tools](docs/mcp.md)
- [Configuration](docs/configuration.md)
- [Docker deployment](docs/docker.md)

## License

[MIT](LICENSE).
