# Python API Reference

## BrowserGoat

`BrowserGoat` is the main entry point. It orchestrates a six-layer search pipeline around a SearXNG instance: query analysis, search, ranking, extraction, reliability checks, optional strategy routing, and optional multi-rollout verification.

```python
from browser_goat import BrowserGoat
```

### Constructor

```python
BrowserGoat(
    searxng_url: str = "http://localhost:8080",
    llm_call: Any = None,
)
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `searxng_url` | `str` | `"http://localhost:8080"` | Base URL of a running SearXNG instance. |
| `llm_call` | `Any` | `None` | Optional async callable for LLM-powered goal-oriented extraction. When provided, extracted sources include structured rational/evidence/summary fields. When omitted, extraction runs without LLM enrichment. |

---

### search()

```python
async def search(
    query: str,
    engines: list[str] | None = None,
    time_range: str | None = None,
    language: str = "en",
    max_sources: int = 15,
    strategy: str = "default",
    reliability_mode: str = "standard",
) -> SearchResult
```

Execute a full search through every active pipeline layer. Returns a `SearchResult` with the synthesized answer, extracted sources, and pipeline metrics.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` | `str` | *(required)* | Natural language search query. |
| `engines` | `list[str] \| None` | `None` | SearXNG engine names to use (e.g. `["google", "bing"]`). When `None`, engines are selected automatically based on the query's detected language. |
| `time_range` | `str \| None` | `None` | Time filter: `"day"`, `"week"`, `"month"`, or `"year"`. Limits results to the given window. |
| `language` | `str` | `"en"` | Language code for results and query analysis. Used for engine selection and language-aware search parameters. |
| `max_sources` | `int` | `15` | Maximum number of page fetches and extractions after ranking. Controls depth-vs-latency trade-off. |
| `strategy` | `str` | `"default"` | Pipeline strategy. See [Strategy modes](#strategy-modes) below. |
| `reliability_mode` | `str` | `"standard"` | Verification intensity. See [Reliability modes](#reliability-modes) below. |

#### Strategy modes

| Value | Behavior |
|---|---|
| `"default"` | Standard pipeline: pre-search → SearXNG → ranking → extraction → reliability. One pass, fastest result. |
| `"auto"` | Classify the query, then route to `"explore"` (for research queries), `"decompose"` (for complex/puzzle queries), or `"default"` (everything else). |
| `"explore"` | Multi-angle adaptive exploration. Generates and searches candidate query variations, then merges the best results. |
| `"decompose"` | Recursive decomposition. Splits complex queries into subtasks, solves each independently, and aggregates. |

#### Reliability modes

| Value | Rollouts | Verification |
|---|---|---|
| `"standard"` | 1 | Single pipeline pass with give-up detection and quality gate. |
| `"high"` | 5 | Five independent searches with consensus voting. Returns the answer agreed upon by at least 4 of 5 rollouts. |
| `"maximum"` | 8 | Eight rollouts with consensus voting plus LLM tie-breaking when no clear winner emerges. |
| `"auto"` | *(routed)* | Behaves like `"standard"`. Reserved for future adaptive routing. |

#### Return type: SearchResult

| Field | Type | Description |
|---|---|---|
| `answer` | `str` | Synthesized answer string built from extracted sources. Includes source citations in `[N]` format. |
| `sources` | `list[ExtractedSource]` | Fully processed sources after extraction and enrichment. See [ExtractedSource](#extractedsource). |
| `query_intent` | `QueryIntent` | Classified intent: `FACTUAL`, `TEMPORAL`, `PERSON`, `COMPARISON`, `HOWTO`, or `RESEARCH`. |
| `engines_used` | `list[str]` | SearXNG engine names used for this search. |
| `total_sources_found` | `int` | Raw result count from SearXNG before filtering. |
| `total_sources_used` | `int` | Number of sources that survived URL cleanup, ranking, and successful extraction. |
| `extraction_success_rate` | `float` | Fraction of ranked URLs whose page content was successfully fetched and extracted. Range 0.0 to 1.0. |
| `pipeline_latency_ms` | `int` | Total pipeline wall-clock time in milliseconds. |
| `reliability` | `ReliabilityInfo` | Aggregated reliability checks. See [ReliabilityInfo](#reliabilityinfo). |
| `timestamp` | `str` | ISO 8601 timestamp of when the result was created. |

---

### extract()

> **Note:** This method is available through the MCP server and CLI interfaces. It fetches and extracts content from a single URL using the same anti-bot bypass and 7-tier extraction stack used internally by `search()`.

```python
async def extract(url: str) -> ExtractedContent
```

#### Return type: ExtractedContent

| Field | Type | Description |
|---|---|---|
| `url` | `str` | The URL that was fetched. |
| `title` | `str` | Page title extracted from `<title>` or structured metadata. Empty string if none found. |
| `text` | `str` | Clean article text. Site chrome, navigation, ads, and sidebars are stripped. |
| `extraction_tier` | `int` | Which of the 7 extraction tiers succeeded. Tier 1 (JSON-LD structured data) is fastest. Tier 7 (full body fallback) is last resort. |
| `word_count` | `int` | Word count of the extracted text. |
| `metadata` | `dict[str, Any]` | Additional metadata discovered during extraction (author, publish date, description, etc.). |

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
async with BrowserGoat(searxng_url="http://localhost:8080") as goat:
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
| `rational` | `str` | Why this page is relevant to the query. Populated when `llm_call` is configured. |
| `evidence` | `str` | Specific text passages from the page that answer the query. Populated when `llm_call` is configured. |
| `summary` | `str` | Condensed 2-3 sentence summary of the page content. |
| `extraction_tier` | `int` | Which extraction tier succeeded (1-7). Lower tiers produce higher-quality content. |
| `used_scrapling` | `bool` | Whether anti-bot bypass was required to fetch this page. |
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
| `quality_retries` | `int` | Number of quality-gate retries used. |
| `force_answer_used` | `bool` | Whether a force-synthesis prompt was used after repeated failures. |

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
| `ConnectionError` | SearXNG is unreachable. Verify the instance is running at the configured `searxng_url`. |
| `TimeoutException` | The search or page fetch exceeded the configured timeout. Increase the timeout or reduce `max_sources`. |

These exceptions are raised by the underlying `httpx.AsyncClient` and propagate directly. Wrap calls in `try`/`except` to handle them:

```python
from browser_goat import BrowserGoat
import httpx

goat = BrowserGoat()

try:
    result = await goat.search("machine learning tutorials")
except httpx.HTTPStatusError as exc:
    print(f"SearXNG error: {exc.response.status_code}")
except ConnectionError:
    print("SearXNG is not running. Start it with: docker compose up")
except TimeoutError:
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
    async with BrowserGoat(searxng_url="http://localhost:8080") as goat:
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

        # With strategy and verification
        result2 = await goat.search(
            "compare Kubernetes and Docker Swarm for small teams",
            strategy="decompose",
            reliability_mode="high",
            time_range="year",
        )
        print(f"\nVerified answer (consensus): {result2.answer[:200]}...")

asyncio.run(main())
```
