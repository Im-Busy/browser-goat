# Configuration

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SEARXNG_URL` | `http://localhost:8080` | SearXNG instance URL |

## SearXNG URL

Set the URL of your SearXNG instance. Must include protocol (`http` / `https`) and port.

```bash
export SEARXNG_URL="http://localhost:8080"
```

Default: `http://localhost:8080`.

## Engine Selection

Override which search engines to query. Default engines come from your SearXNG instance's `settings.yml`.

```bash
browser-goat search "query" --engines google bing duckduckgo
```

## Language

Set the search language with an ISO 639-1 code. CJK queries (Chinese, Japanese, Korean) are detected automatically and receive adjusted search parameters for better results.

```bash
browser-goat search "query" --language fr
```

Default: `en`.

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
| `decompose` | Break complex queries into subtasks, then aggregate results |

## Max Sources

Cap the number of unique sources fetched and extracted per query.

```bash
browser-goat search "query" --max-sources 10
```

Default: `15`.
