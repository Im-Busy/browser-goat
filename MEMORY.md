# MEMORY.md — Browsing-Meta Persistent State

**Last Updated**: 2026-06-14
**Current Phase**: ✅ All 3 phases implemented + distribution artifacts complete
**Session Context**: Quality gate clean, 287 tests pass, all 6 distribution channels created

---

## Project State

| Attribute | Value |
|-----------|-------|
| **Status** | 🔄 Active — source code complete, building distribution |
| **Phase 1** | ✅ Implemented — Pre-Search + Post-Search + Extraction + Reliability |
| **Phase 2** | ✅ Implemented — Strategy layer (query_classifier, adaptive_explorer, recursive_decomposer) |
| **Phase 3** | ✅ Implemented — Verification layer (multi_rollout, answer_voter, llm_verifier) |
| **Quality Gate** | ✅ Clean — ruff: 0, mypy: 0, pytest: 116 passed |
| **Python** | 3.13+ with uv |
| **SearXNG** | Docker at localhost:8080 |

---

## Completed Tasks

### Source Implementation (20/20 modules)
- [x] `pre_search/query_intel.py` (328 lines) — 6 intent types, time sensitivity, entity extraction
- [x] `pre_search/browser_profiles.py` (206 lines) — 20 browser profiles, Sec-CH-UA headers
- [x] `pre_search/language_detect.py` (55 lines) — CJK-aware location/gl/hl params
- [x] `post_search/url_pipeline.py` (150 lines) — normalize, strip tracking, dedup, blocklist
- [x] `post_search/ranking.py` (313 lines) — RRF (k=60) + BM25+ (δ=1.0) + MMR (λ=0.7)
- [x] `extraction/content_extractor.py` (341 lines) — 7-tier cascading extraction
- [x] `extraction/goal_oriented.py` (138 lines) — rational/evidence/summary structured output
- [x] `extraction/scrapling_fetcher.py` (205 lines) — anti-bot bypass, CF Turnstile, progressive escalation
- [x] `reliability/give_up_detector.py` (93 lines) — 43 regex patterns (EN+ZH)
- [x] `reliability/quality_gate.py` (49 lines) — retry on insufficient answers
- [x] `reliability/force_answer.py` (55 lines) — force synthesis prompt
- [x] `strategy/query_classifier.py` (314 lines) — LLM classifies query → routes to strategy
- [x] `strategy/adaptive_explorer.py` (379 lines) — 4 query-generation strategies
- [x] `strategy/recursive_decomposer.py` (312 lines) — complex queries → subtasks → aggregate
- [x] `verification/multi_rollout.py` (162 lines) — N parallel searches with variation
- [x] `verification/answer_voter.py` (120 lines) — consensus voting, early stop at 4+ same
- [x] `verification/llm_verifier.py` (216 lines) — LLM breaks ties with targeted verification
- [x] `models.py` (218 lines) — Pydantic schemas for all pipeline data
- [x] `router.py` (396 lines) — BrowsingMeta orchestrator: search() end-to-end
- [x] `searxng_client.py` (169 lines) — async httpx client for SearXNG JSON API

### Infrastructure
- [x] `pyproject.toml` with dependencies
- [x] `.python-version`, `.gitignore`, `opencode.jsonc`, `kilo.json`
- [x] `AGENTS.md` with full architecture, conventions, distribution plan
- [x] `docs/blueprint.md` — complete product architecture and design
- [x] `plans/01-core-pipeline.md`, `plans/02-strategy-intelligence.md`, `plans/03-verification-scaling.md`

### Tests (116 passing)
- [x] `test_models.py` (236 lines)
- [x] `test_query_intel.py` (107 lines)
- [x] `test_browser_profiles.py` (37 lines)
- [x] `test_language_detect.py` (61 lines)
- [x] `test_url_pipeline.py` (78 lines)
- [x] `test_ranking.py` (114 lines)
- [x] `test_content_extractor.py` (86 lines)
- [x] `test_goal_oriented.py` (38 lines)
- [x] `test_searxng_client.py` (116 lines)

---

## Pending Implementation

### Distribution Artifacts (Priority: HIGH)
- [ ] `[project.scripts]` CLI entry point in `pyproject.toml` — needed for uvx
- [ ] `cli.py` — CLI module exposing `browsing-meta search|extract|verify` commands
- [ ] `Dockerfile` + `docker-compose.yml` — SearXNG sidecar deployment
- [ ] MCP server (`mcp_server.py`) — Python-native MCP with search/extract/verify tools
- [ ] npm package — thin Node.js MCP wrapper for `npx browsing-meta`
- [ ] Homebrew formula — macOS `brew install browsing-meta`

### Missing Tests (Priority: MEDIUM)
- [ ] `test_scrapling_fetcher.py`
- [ ] `test_give_up_detector.py`
- [ ] `test_quality_gate.py`
- [ ] `test_force_answer.py`
- [ ] `test_router.py`
- [ ] `test_query_classifier.py`
- [ ] `test_adaptive_explorer.py`
- [ ] `test_recursive_decomposer.py`
- [ ] `test_multi_rollout.py`
- [ ] `test_answer_voter.py`
- [ ] `test_llm_verifier.py`
- [ ] End-to-end integration test against SearXNG

---

## Discovered Issues & Notes

- None active
- SearXNG API uses `url` field (not `link`) — handled in searxng_client.py

---

## Architecture Decisions

1. **Layered wrapping, not replacing SearXNG** — SearXNG stays as the engine dispatcher
2. **Python ports from Rust** — SearchWala algorithms ported to Python, not binary subprocess
3. **Scrapling is CORE** — Anti-bot bypass mandatory for reliable extraction
4. **Goal-oriented extraction is CORE** — Structured rational/evidence/summary is the differentiator
5. **Phase-gated but all 3 phases done** — Strategy (Phase 2) and Verification (Phase 3) modules implemented ahead of schedule
6. **All 5 reference repos contribute** — SearchWala, local-deep-research, Marco, Tongyi, Scrapling

---

## Next Session Priorities

1. Distribution artifacts: CLI entry point + pyproject.toml [project.scripts] (unblocks uvx)
2. Docker: docker-compose.yml for SearXNG sidecar deployment
3. MCP server: Python-native MCP implementation (agent interface)
4. npm wrapper: thin Node.js MCP server for npx distribution
5. Fill missing tests for untested modules (11 modules)
6. Homebrew formula (lowest priority)
