# Python API Reference

## BrowserGoat

`BrowserGoat` is the main entry point for query analysis, SearXNG search,
ranking, page extraction, and quality checks. Strategy routing and
multi-rollout verification wrap that path; they are optional.

```python
from browser_goat import BrowserGoat
```

### Constructor

```python
BrowserGoat(
    searxng_url: str | None = None,
    llm_call: Any = None,
    cache_ttl_seconds: float | None = None,
    cache_max_entries: int | None = None,
)
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `searxng_url` | `str \| None` | `None` | Explicit URL, otherwise `SEARXNG_URL`, otherwise `http://localhost:8082`. |
| `llm_call` | `Any` | `None` | Optional async chat callback for extraction enrichment, classification, exploration, decomposition, and verification. Without it, source fields contain text excerpts and decomposition falls back to default search. |
| `cache_ttl_seconds` | `float \| None` | `None` | Override `CONTENT_CACHE_TTL_SECONDS` (default 900); non-negative. |
| `cache_max_entries` | `int \| None` | `None` | Override `CONTENT_CACHE_MAX_ENTRIES` (default 256); non-negative. |

`llm_call` receives a list of chat messages and returns a string asynchronously.
It is shared by goal extraction, classification, exploration, decomposition,
and the adapted verifier. Without it, only the verifier can use
`BROWSER_GOAT_LLM`; other stages stay rule-based. Source evidence and summaries
then contain bounded excerpts, not LLM-generated assertions.

---

### search()

```python
async def search(
    query: str,
    engines: list[str] | None = None,
    time_range: str | None = None,
    language: str = "auto",
    max_sources: int = 15,
    strategy: str = "default",
    reliability_mode: str = "standard",
) -> SearchResult
```

Return a `SearchResult` with an answer, extracted sources, and pipeline metrics.
Default and explore answers list up to five sources and up to 200 characters
of each summary. Without `llm_call`, the summaries use extracted-text excerpts.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` | `str` | *(required)* | Natural language search query. |
| `engines` | `list[str] \| None` | `None` | SearXNG engine names to use (e.g. `["google", "bing"]`). When `None`, engines are selected automatically based on the query's detected language. |
| `time_range` | `str \| None` | `None` | Time filter: `"day"`, `"week"`, `"month"`, or `"year"`. Limits results to the given window. |
| `language` | `str` | `"auto"` | Detect from query; an explicit code overrides detection. |
| `max_sources` | `int` | `15` | 1-50 page extractions per pass, including each verification rollout. |
| `strategy` | `str` | `"default"` | Pipeline strategy. See [Strategy modes](#strategy-modes) below. |
| `reliability_mode` | `str` | `"standard"` | Verification intensity. See [Reliability modes](#reliability-modes) below. |

#### Strategy modes

| Value | Behavior |
|---|---|
| `"default"` | One search pass: query analysis, SearXNG, ranking, extraction, and quality checks. |
| `"auto"` | Classify the query, then route to `"explore"` (for research queries), `"decompose"` (for complex/puzzle queries), or `"default"` (everything else). |
| `"explore"` | Multi-angle adaptive exploration. Generates and searches candidate query variations, then merges the best results. |
| `"decompose"` | Recursive subtasks and LLM synthesis from SearXNG result snippets with `llm_call`. The router then extracts the collected pages. Falls back to default search without the callback. |
| `"direct"` | Alias for `"default"`. |

#### Reliability modes

| Value | Rollouts | Verification |
|---|---|---|
| `"standard"` | 1 | Single pipeline pass with give-up detection and quality gate. |
| `"high"` | up to 5 | Consensus at four matching answers; otherwise returns the plurality or a tied candidate. |
| `"maximum"` | up to 8 | Consensus voting plus optional LLM tie-breaking; no LLM means an explicit fallback. |
| `"auto"` | *(adaptive)* | Adaptively selects mode based on query complexity and intent classification. |

#### Return type: SearchResult

| Field | Type | Description |
|---|---|---|
| `answer` | `str` | Default/explore source listing with `[N]` links and summary excerpts; decomposition can return a callback-generated answer based on search snippets. |
| `sources` | `list[ExtractedSource]` | Fully processed sources after extraction and enrichment. See [ExtractedSource](#extractedsource). |
| `query_intent` | `QueryIntent` | Classified intent: `FACTUAL`, `TEMPORAL`, `PERSON`, `COMPARISON`, `HOWTO`, or `RESEARCH`. |
| `engines_used` | `list[str]` | SearXNG engine names used for this search. |
| `total_sources_found` | `int` | Raw result count from SearXNG before filtering. |
| `total_sources_used` | `int` | Number of sources that survived URL cleanup, ranking, and successful extraction. |
| `extraction_success_rate` | `float` | Fraction of ranked URLs whose page content was successfully fetched and extracted. Range 0.0 to 1.0. |
| `pipeline_latency_ms` | `int` | Total pipeline wall-clock time in milliseconds. |
| `reliability` | `ReliabilityInfo` | Aggregated reliability checks. See [ReliabilityInfo](#reliabilityinfo). |
| `verification` | `VerificationResult \| None` | Vote outcome and collection/deadline metadata for a verified search; otherwise `None`. |
| `timestamp` | `str` | ISO 8601 timestamp of when the result was created. |

---

### extract()

Available in the library, CLI, and MCP. It shares the HTML cache with search.

```python
async def extract(url: str) -> dict[str, Any]
```

#### Return fields

| Field | Type | Description |
|---|---|---|
| `url` | `str` | The URL that was fetched. |
| `title` | `str` | Page title extracted from `<title>` or structured metadata. Empty string if none found. |
| `text` | `str` | Extracted page text. Later fallback tiers can retain navigation or other site text. |
| `extraction_tier` | `int` | First successful text-extraction tier, from 1 (JSON-LD) through 7 (body fallback). Tier order is not a measured speed or quality guarantee. |
| `text_length` | `int` | Length of the full returned text. |
| `success` | `bool` | False when fetching fails or no text can be extracted. |
| `error` | `str \| None` | Failure description. Fetch failures omit the text fields. |

### verify() and cache helpers

`await goat.verify(query, rollouts=5)` accepts 3-8 rollouts. It returns the
search-result fields plus `query`, `rollouts_run`, `vote_counts`, and
`candidates`. Verification metadata records actual completions, agreement,
and the method (`consensus`, `llm`, `fallback`, or `rollout_failure`). Failed
quality checks are not votes; one surviving result is not consensus. The
selected answer retains its own source list and metrics.

Voting groups answers by exact text after trimming outer whitespace and
lowercasing. Four matching answers establish consensus. Collection and optional
tie-breaking share a 40-second budget; failures and the deadline can reduce
completions. Pending work is cancelled and drained, which can add latency.
See [verification metadata](mcp.md#verification-deadline-and-partial-results).

`goat.cache_stats()` returns hits, misses, size, capacity, TTL, and hit rate.
`goat.clear_cache()` clears cached HTML and resets counters.
Concurrent misses for one exact URL share a bounded in-flight task. Failures
are not cached. Cancelling a waiter leaves other consumers running; the last
waiter cancels and drains the fetch. `close()` drains all outstanding fetches
and is terminal for that instance. See [cache configuration](configuration.md#reliability-and-cache).

---

### close()

```python
async def close() -> None
```

Close all internal HTTP clients and release resources. Call this when you are done with the instance, or use the async context manager pattern.

---

### Async context manager

The preferred way to use `BrowserGoat` is as an async context manager, which ensures `close()` is called automatically:

```python
async with BrowserGoat(searxng_url="http://localhost:8082") as goat:
    result = await goat.search("quantum computing breakthroughs 2026")
    print(result.answer)
    for source in result.sources:
        print(f"  [{source.rank}] {source.title}")
```

When an async context manager is not practical, use explicit `close()`:

```python
goat = BrowserGoat()
try:
    result = await goat.search("latest AI research")
    print(result.answer)
finally:
    await goat.close()
```

---

## Models

### ExtractedSource

A single processed search result after extraction and enrichment. Each source in `SearchResult.sources` is an `ExtractedSource`.

| Field | Type | Description |
|---|---|---|
| `url` | `str` | Source URL. |
| `title` | `str` | Page title. |
| `rational` | `str` | Callback-generated rationale, or a generic relevance message on the no-LLM/fallback path. |
| `evidence` | `str` | Callback-generated evidence, or up to 2,000 characters of extracted text on the no-LLM/fallback path. |
| `summary` | `str` | Callback-generated summary, or up to 500 characters of extracted text on the no-LLM/fallback path. |
| `extraction_tier` | `int` | First successful text-extraction tier (1-7); not a quality score. |
| `used_scrapling` | `bool` | True when the fetch reports Scrapling or Crawl4AI use. False for cache hits; not proof that anti-bot bypass was necessary or successful. |
| `rank` | `int` | Position in the ranked results (1-indexed). |
| `final_score` | `float` | Composite relevance score from the hybrid ranker. |
| `engine` | `str` | SearXNG engine that returned this result (e.g. `"google"`, `"bing"`). |

### ReliabilityInfo

Aggregated reliability checks applied to every search result.

| Field | Type | Description |
|---|---|---|
| `give_up_detected` | `bool` | Whether the answer matched a known give-up pattern (e.g. "I couldn't find any results"). |
| `give_up_pattern` | `str \| None` | The specific regex pattern that matched, if any. |
| `quality_passed` | `bool` | Whether the answer passed the quality gate (minimum length, citation presence). |
| `quality_retries` | `int` | Zero for the basic pipeline, which does not retry synthesis. |
| `force_answer_used` | `bool` | False when no force synthesis was performed. |

### QueryIntent

Enum of classified query intents, available as `SearchResult.query_intent`.

| Value | Description |
|---|---|
| `QueryIntent.FACTUAL` | "What is the capital of France?" Fact lookups. |
| `QueryIntent.TEMPORAL` | "What happened today?" Time-sensitive questions. |
| `QueryIntent.PERSON` | "Who is Satya Nadella?" Entity lookups. |
| `QueryIntent.COMPARISON` | "Python vs Rust for web dev" Comparative questions. |
| `QueryIntent.HOWTO` | "How to deploy a Docker container?" Procedural questions. |
| `QueryIntent.RESEARCH` | "Latest research on quantum computing" Open-ended investigation. |

---

## Errors

All search operations may raise the following exceptions:

| Exception | Cause |
|---|---|
| `httpx.HTTPStatusError` | SearXNG returned a non-2xx status code. Check that the instance is running and the URL is correct. |
| `httpx.ConnectError` | SearXNG is unreachable. Check the configured URL and backend service. |
| `httpx.TimeoutException` | The SearXNG request timed out. |
| `ValueError` | Invalid query/options or malformed SearXNG JSON. |

These exceptions are raised by the underlying `httpx.AsyncClient` and propagate directly. Wrap calls in `try`/`except` to handle them:

```python
from browser_goat import BrowserGoat
import httpx

goat = BrowserGoat()

try:
    result = await goat.search("machine learning tutorials")
except httpx.HTTPStatusError as exc:
    print(f"SearXNG error: {exc.response.status_code}")
except httpx.ConnectError:
    print("SearXNG is not running. Start it with: docker compose up")
except httpx.TimeoutException:
    print("Search timed out. Try a narrower query or reduce max_sources.")
finally:
    await goat.close()
```

---

## Complete example

```python
import asyncio
from browser_goat import BrowserGoat

async def main() -> None:
    async with BrowserGoat(searxng_url="http://localhost:8082") as goat:
        # Basic search
        result = await goat.search("Python async programming patterns")

        print(f"Intent: {result.query_intent}")
        print(f"Found {result.total_sources_found} sources, used {result.total_sources_used}")
        print(f"Extraction rate: {result.extraction_success_rate:.0%}")
        print(f"Latency: {result.pipeline_latency_ms}ms")
        print()

        print(result.answer)
        print()

        for source in result.sources[:3]:
            print(f"[{source.rank}] {source.title}")
            print(f"    {source.url}")
            if source.summary:
                print(f"    {source.summary[:120]}...")

        # Request voting across multiple searches.
        result2 = await goat.search(
            "compare Kubernetes and Docker Swarm for small teams",
            strategy="explore",
            reliability_mode="high",
            time_range="year",
        )
        print(result2.answer[:200])
        print(result2.verification)

asyncio.run(main())
```
