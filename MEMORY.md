# MEMORY.md — browser-goat Persistent State

**Last Updated**: 2026-06-19
**Current Phase**: ✅ All 3 phases implemented + distribution artifacts complete
**Dual-Repo**: ✅ Applied — private `master` + public `public` branches

---

## Project State

| Attribute | Value |
|-----------|-------|
| **Status** | 🔄 Active — polishing distribution |
| **Phase 1** | ✅ Implemented — Pre-Search + Post-Search + Extraction + Reliability |
| **Phase 2** | ✅ Implemented — Strategy layer (query_classifier, adaptive_explorer, recursive_decomposer) |
| **Phase 3** | ✅ Implemented — Verification layer (multi_rollout, answer_voter, llm_verifier) |
| **Quality Gate** | ✅ Clean — ruff: 0, mypy: 0, pytest: 304 passed (287 unit + 17 integration) |
| **Python** | 3.13+ with uv |
| **SearXNG** | Docker at localhost:8080 |

---

## Completed Tasks

### Source Implementation (20/20 modules)
All 20 modules implemented across all 6 layers. See AGENTS.md for architecture details.

### Distribution Channels (6/6)
- [x] PyPI — `pip install browser-goat` (via pyproject.toml + [project.scripts])
- [x] uvx — `uvx browser-goat` and `uvx browser-goat-mcp` (CLI + MCP entry points)
- [x] Docker — `docker compose up` (SearXNG + browser-goat sidecar)
- [x] MCP Server — Python-native MCP (mcp_server.py) + npm thin wrapper (npm/index.js)
- [x] npm/npx — `npx browser-goat` (thin Node.js MCP wrapper)
- [x] Homebrew — Formula in separate tap repo
- [x] distribution/ — Per-platform MCP config snippets (Claude Desktop, Cursor, OpenCode, Copilot, Windsurf)

### Infrastructure
- [x] Dual-repo setup — private + public remotes, public branch, whitelist.txt, sync infrastructure
- [x] pyproject.toml — classifiers, [project.urls], authors, readme, [project.scripts]
- [x] distribution/ — platform MCP config snippets

### Tests (304 passing — 287 unit + 17 integration)
All 20 modules have corresponding test files. Integration tests require SearXNG at localhost:8080.

---

## Pending Implementation

None. All planned features and distribution channels are complete.

---

## Discovered Issues & Notes

- None active
- SearXNG API uses `url` field (not `link`) — handled in searxng_client.py
- homebrew/ formula lives in separate tap repo (removed from this repo in commit 26614fb)

---

## Architecture Decisions

1. **Layered wrapping, not replacing SearXNG** — SearXNG stays as the engine dispatcher
2. **Python ports from Rust** — SearchWala algorithms ported to Python, not binary subprocess
3. **Scrapling is CORE** — Anti-bot bypass mandatory for reliable extraction
4. **Goal-oriented extraction is CORE** — Structured rational/evidence/summary is the differentiator
5. **Phase-gated but all 3 phases done** — Strategy (Phase 2) and Verification (Phase 3) modules implemented ahead of schedule
6. **All 5 reference repos contribute** — SearchWala, local-deep-research, Marco, Tongyi, Scrapling
7. **Dual-repo architecture** — Private `master` for development, public `public` branch for distribution

---

## Repository Architecture

- **Private remote**: `private` → `https://github.com/Im-Busy/browser-goat.git` (branch: `master`)
- **Public remote**: `public` → `https://github.com/Im-Busy/browser-goat.git` (branch: `public`)
- **Sync**: `/sync` — merge master → public, strip private files, push
- **Whitelist**: `whitelist.txt` defines public file inventory
- **Private files**: MEMORY.md, plans/, docs/blueprint.md, .omo/, kilo.json, opencode.jsonc, .python-version
