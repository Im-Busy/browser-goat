# MCP integration

The Python MCP server exposes `search`, `extract`, and `verify` over stdio.
SearXNG must be running with JSON search enabled for search and verification.
Extraction does not require SearXNG.

## Start the server

```bash
uvx --from browser-goat browser-goat-mcp --searxng-url http://localhost:8082
```

From a source checkout, use `uv run browser-goat-mcp` after syncing dependencies.
Do not send ordinary CLI output over an MCP stdio channel.

For clients supporting the `mcpServers` format:

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

Client configuration formats differ; this is not a universal harness schema.
The npm alternative, `npx browser-goat`, requires an installed Python backend;
see [npm setup](../npm/README.md). No MCP HTTP endpoint is started by the
bundled Compose stack. Its port `8003` is the separate HTTP JSON API.

## Tool reference

| Tool | Inputs | Output |
|---|---|---|
| `search` | `query`; `time_range` (day/week/month/year or null); `max_sources` (1-50, default 15); `strategy` (auto/default/direct/explore/decompose); `reliability_mode` (standard/high/maximum/auto) | SearchResult fields: answer, sources, reliability, optional verification, and metrics |
| `extract` | `url` (HTTP or HTTPS) | Full text, title, extraction tier, text length, success, error |
| `verify` | `query`; `rollouts` (3-8, default 5); optional `searxng_url` override | SearchResult fields plus query, rollouts_run, vote_counts, candidates |

`search` defaults to strategy `auto` and reliability `standard`. Invalid options
are rejected rather than silently clamped. Extraction failures return
`success=false`; empty text is not reported as success.

Four matching normalized answers establish consensus. Lower-count pluralities
are retained without consensus; one surviving result is never consensus.
Quality failures do not vote. With more than five requested rollouts, a tie
can use an explicitly configured verifier LLM. Without one, verification
reports `method="fallback"`, not `llm`. Actual completions are reported, not the
requested count. Agreement is not proof of correctness.

### Verification deadline and partial results

`verify` requests three source pages per rollout rather than the normal search
default of 15. This bounds requested pages to 9-24 and leaves more time for the
highest-ranked sources. `search` in high/maximum reliability mode preserves its
explicit `max_sources`; it is not silently reduced.

All verification calls have a **40-second shared collection budget**. Pending
rollouts, extraction tasks, and fetches with no remaining consumers are cancelled
and drained at the deadline. An optional LLM tie-breaker uses only the remaining
budget; if it times out, the voted fallback is retained. Cancellation cleanup
can add latency beyond 40 seconds. A backend that does not cooperate with
cancellation can still delay cleanup; the budget is not a hard MCP transport SLA.

| Verification field | Meaning |
|---|---|
| `rollout_count` | Completed SearchResult objects, also exposed as `rollouts_run` |
| `requested_rollouts` | Requested count before early stop |
| `failed_rollouts` | Rollouts that raised an exception during collection |
| `cancelled_rollouts` | Rollouts cancelled before completion |
| `timed_out` | Collection or optional tie-breaking exhausted its time budget |
| `partial` | Fewer SearchResult objects collected than requested, including early consensus |
| `stop_reason` | `completed`, `consensus`, `deadline`, or `verifier_timeout` |
| `timeout_seconds` | Shared collection budget, currently 40 |

Completed answers are preserved on timeout. Fewer than four matching votes are
not consensus. If no usable answer completed, the response has empty sources,
`verification.method="rollout_failure"`, and `reliability.quality_passed=false`.
Inspect these fields instead of treating a successful protocol response as proof
that verification succeeded. No LLM service is required for this policy.

`decompose` requires an explicit library chat callback. The stdio server does
not configure that callback and therefore uses default search for this mode.
`BROWSER_GOAT_LLM` only configures the optional verification tie-breaker.

## Troubleshooting

- `Cannot connect to SearXNG`: confirm the backend at `SEARXNG_URL`, independently
  of whether MCP initialization and tool discovery work.
- HTTP 403 from `/search`: enable `json` under SearXNG `search.formats`.
- Browser-tier import or executable errors: sync the declared dependencies and
  install the browser binaries in [installation](install.md).
- A repaired source file does not reload a running MCP process. Restart the
  server, then reconnect the client. On Windows, stop the server before
  dependency sync to release locked executables.

Offline protocol checks: `uv run pytest tests/test_interfaces.py -k mcp`.
They perform real Python/npm stdio handshakes and tool calls against a local
HTTP fixture, not external engines or a harness's exposed MCP connection.
