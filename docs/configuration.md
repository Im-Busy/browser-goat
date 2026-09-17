# Configuration

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SEARXNG_URL` | `http://localhost:8082` | SearXNG instance URL |
| `CONTENT_CACHE_TTL_SECONDS` | `900` | HTML cache TTL; finite non-negative seconds; `0` disables reuse |
| `CONTENT_CACHE_MAX_ENTRIES` | `256` | HTML cache capacity; non-negative integer; `0` disables storage |
| `CRAWL4AI_PROXY_LIST` | empty | Comma-separated proxies for the Crawl4AI tier |
| `BROWSER_GOAT_LLM` | empty | Optional verifier provider (`ollama:llama3` or `openai:<model>`); does not enable other LLM stages |
| `BROWSER_GOAT_OLLAMA_HOST` | `http://localhost:11434` | Ollama endpoint |
| `BROWSER_GOAT_OPENAI_API_KEY` | empty | OpenAI verifier credential; `OPENAI_API_KEY` is a fallback |

## SearXNG URL

Set the URL of your SearXNG instance. Must include protocol (`http` / `https`) and port.

```bash
export SEARXNG_URL="http://localhost:8082"
```

Default: `http://localhost:8082`.

## Engine Selection

Override which search engines to query. When omitted, browser-goat selects engines
from the detected language. Engines must also be available in SearXNG.

An explicit engine list can select an engine that SearXNG marks disabled by
default. Disabling an engine's default selection alone does not prevent
browser-goat's language presets or verification subsets from requesting it.
Pass a known-good list explicitly when diagnosing engine behavior. An empty
list (`--engines` with no values in the CLI, `engines=[]` in the library)
leaves engine selection to SearXNG. Ranking is not a semantic relevance gate:
irrelevant upstream results can receive zero scores and still be returned.

```bash
browser-goat search "query" --engines google bing duckduckgo
```

## Language

Set the search language with an ISO 639-1 code. CJK queries (Chinese, Japanese, Korean) are detected automatically and receive adjusted search parameters for better results.

```bash
browser-goat search "query" --language fr
```

Default: `auto`. An explicit language such as `fr` overrides detection in all
search paths, including exploration and verification.

## Time Range

Limit results to a time window.

```bash
browser-goat search "query" --time-range week
```

| Value | Window |
|-------|--------|
| `day` | Past 24 hours |
| `week` | Past 7 days |
| `month` | Past ~30 days |
| `year` | Past 365 days |

## Strategy

Choose how browser-goat processes your query.

```bash
browser-goat search "query" --strategy explore
```

| Strategy | Behavior |
|----------|----------|
| `default` | Standard pipeline — fast, suited for simple queries |
| `auto` | Auto-detect the best strategy based on query complexity |
| `explore` | Adaptive multi-angle exploration for deeper research |
| `decompose` | Recursive subtasks with a library `llm_call`; otherwise default search |
| `direct` | Alias for `default` |

## Max Sources

Cap the number of unique sources fetched and extracted per query.

```bash
browser-goat search "query" --max-sources 10
```

Default: `15`; allowed range: `1`-`50`. The bound applies to each verification
rollout. Explicit engines, language, time range, source limit, and strategy
are preserved across rollouts.

## Reliability and cache

`standard` checks a single answer. `high` requests five rollouts; `maximum`
requests eight and permits an optional LLM tie-breaker. Early consensus can
reduce actual completions. Without an LLM, ties return `method="fallback"`.
Quality checks do not perform automatic synthesis retries.

The HTML cache belongs to one `BrowserGoat` instance. MCP and HTTP servers
reuse it; separate CLI processes do not. It stores accepted HTML, not LLM
answers. Concurrent misses for the same exact URL share one in-flight fetch,
including its failure. Failures are not cached, so a later call can retry.
At most 256 distinct URLs are tracked in-flight; further URLs wait for a slot.
Cancelling one waiter does not abort other consumers. When the last waiter
cancels, the fetch is cancelled and drained; `close()` drains all in-flight
work. Use `cache_stats()` and `clear_cache()` in the library. Cache-hit fetch
metadata is synthetic (`fetch_tier=0`), so it
does not preserve the original browser backend flags.

Every fetch tier requires HTTP success, nonblank content, and no recognized
challenge/interstitial or JavaScript-only shell. Rejected pages continue to
the next tier and are not cached. Detection is conservative: documentation
mentioning CAPTCHA or JavaScript is not itself a challenge. Unknown anti-bot
pages may still require manual inspection.
