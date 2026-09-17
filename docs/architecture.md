# Architecture

browser-goat wraps SearXNG with query analysis, result ranking, page extraction,
and quality checks. Optional strategies expand queries or compare answers from
multiple searches. Agreement between searches is not proof of factual accuracy.

## Entry points

The library, CLI, HTTP JSON API, and MCP stdio server share the
[`BrowserGoat` implementation](../src/browser_goat/router.py).

| Interface | Implementation | Reference |
|---|---|---|
| Python library | [`router.py`](../src/browser_goat/router.py) | [Python API](library.md) |
| CLI | [`cli.py`](../src/browser_goat/cli.py) | [CLI and HTTP API](cli.md) |
| HTTP JSON API | [`api.py`](../src/browser_goat/api.py) | [Deployment](deployment.md) |
| MCP stdio | [`mcp_server.py`](../src/browser_goat/mcp_server.py) | [MCP integration](mcp.md) |
| Node.js launcher | [`npm/index.js`](../npm/index.js) | [npm prerequisites](../npm/README.md) |

The Node.js launcher starts the Python MCP server; it is not a separate search
implementation. The HTTP API and MCP server use different transports. Compose
starts the HTTP API, not an MCP endpoint.

## Default search path

1. Validate the search options before network requests.
2. Analyze the query, choose language parameters and request headers, and send
   the query to SearXNG's JSON search API.
3. Normalize result URLs, remove tracking parameters, and identify blocked or
   duplicate results. The ranker excludes those results before scoring.
4. Rank eligible results with reciprocal rank fusion (RRF), BM25+, and maximal
   marginal relevance (MMR). These scores order results; they do not certify
   relevance or correctness.
5. Fetch selected pages and extract text. Build source records with `rational`,
   `evidence`, and `summary` fields. An explicit library LLM callback can enrich
   these fields; the no-LLM path uses extracted text.
6. Build an answer from source summaries and report quality and give-up checks.
   The basic pipeline does not retry synthesis or force an answer.

The result includes the answer, sources, reliability fields, extraction success
rate, and elapsed pipeline time. See the [data models](../src/browser_goat/models.py)
for the response fields and [ranking implementation](../src/browser_goat/post_search/ranking.py)
for scoring parameters.

## Strategy and verification

Strategy dispatch and verification wrap the default path; they are not six
unconditional sequential stages.

| Option | Behavior |
|---|---|
| `default` or `direct` | Run one search pass with ranking, extraction, and quality checks. |
| `explore` | Merge results from query variants before ranking. Without an LLM callback, use the direct query and available rule-based synonyms. |
| `decompose` | Use an explicit library chat callback to split and aggregate subtasks. Without the callback, fall back to default search. |
| `auto` strategy | Choose a strategy from query classification. |
| `high` reliability | Request five rollouts and vote across usable answers. |
| `maximum` reliability | Request eight rollouts; differing candidates can use an optional configured verifier. |

Four matching normalized answers establish consensus and can stop pending
rollouts. Answers that fail quality checks do not vote. Lower-count pluralities
remain fallback results, not consensus. Results report actual completed
rollouts, preserve caller search constraints, and retain the selected answer's
sources. Pending rollout tasks are cancelled and awaited on early stop or
caller cancellation.

`BROWSER_GOAT_LLM` configures the optional verification provider. It does not
supply the library chat callback needed for decomposition or extraction
enrichment. Without a configured verifier, tie-breaking reports `fallback`,
not `llm`. See [configuration](configuration.md) and [MCP integration](mcp.md).

## Fetching and extraction

The [page fetcher](../src/browser_goat/extraction/scrapling_fetcher.py) tries these
backends in order until a response passes its acceptance checks:

1. HTTPX with browser-profile headers.
2. Scrapling's stealth browser fetcher.
3. Scrapling with challenge solving requested.
4. Crawl4AI with Shadow DOM flattening and optional configured proxy rotation.
5. Playwright Chromium.
6. Plain HTTPX without the browser profile.

Each tier has its own deadline, capped at 15 seconds. This is not an
end-to-end request deadline. Browser-backed tiers need their Python dependencies,
browser binaries, and operating-system libraries. No proxy service is bundled,
and the adapter does not enable automatic proxy escalation or browser recycling.
Access to a protected site is not guaranteed.

All tiers use a shared [response acceptance check](../src/browser_goat/extraction/response_acceptance.py).
Blank responses, recognized challenge pages, and JavaScript-only shells cause
escalation rather than cache insertion. This heuristic does not detect every
challenge or establish topical relevance.

After fetching, the [content extractor](../src/browser_goat/extraction/content_extractor.py)
tries JSON-LD, structured CSS, semantic HTML, scored containers, content elements,
metadata, and body text. Fetch tiers and text-extraction tiers are separate.

## Cache and lifecycle

Each `BrowserGoat` instance has an in-memory [TTL cache](../src/browser_goat/cache.py)
of accepted HTML, keyed by exact fetch URL. Calls and rollouts on that instance
share cached content and in-flight fetches. Cache hits contain synthetic fetch
metadata, not the original backend flags.

Concurrent misses for one URL share a task. Failures are shared with current
waiters but are not cached. Cancelling one waiter does not cancel other waiters;
the last waiter cancels and drains unfinished work. The instance limits active
page fetches to eight and distinct in-flight URLs to 256, with backpressure.
The cache defaults to a 900-second TTL and 256 entries; see
[configuration](configuration.md) for overrides.

Use `async with BrowserGoat(...)` or call `await close()` to drain outstanding
fetches and close HTTP clients. Each MCP server captures its own backend and
closes it at lifespan shutdown.

## Trust boundaries

Page content and search results are untrusted input. Quality checks, extraction
success, ranking scores, and consensus are diagnostics, not security or truth
guarantees. The HTTP API has no authentication. Native listeners bind to
loopback by default; Compose publishes loopback host ports. Keep access restricted
and review network permissions before allowing untrusted callers to submit URLs.

See [deployment](deployment.md) for startup and health checks, and
[the README's verification section](../README.md#development-and-verification)
for the distinction between offline tests and live backend checks.
