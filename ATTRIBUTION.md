# Third-Party Attributions

browser-goat is licensed under the MIT License. It adapts algorithms and patterns
from the following third-party projects, each under its own license:

## SearchWala
- **License**: Apache-2.0
- **Copyright**: Copyright 2026 Sandeep
- **Adapted**: Query intent detection, browser profiles, URL normalization, hybrid ranking (RRF + BM25+ + MMR), 7-tier cascading content extraction, quality-gated retry
- **Modified**: Yes — algorithms ported from Rust to Python, restructured for integration pipeline

## local-deep-research
- **License**: MIT
- **Copyright**: Copyright 2025 LearningCircuit
- **Adapted**: Query classification, adaptive exploration strategies, recursive decomposition
- **Modified**: Yes — restructured for pipeline integration, Python adapters

## Marco-DeepResearch
- **License**: Apache-2.0
- **Adapted**: Give-up detection patterns, multi-rollout voting, force-answer synthesis, LLM tie-breaking verification
- **Modified**: Yes — ported from context manager to standalone pipeline modules

## Tongyi-DeepResearch
- **License**: Apache-2.0
- **Adapted**: Language-aware search parameters (CJK detection), goal-oriented extraction (Rational/Evidence/Summary)
- **Modified**: Yes — integrated into pre-search and extraction pipeline stages

## Scrapling
- **License**: BSD-3-Clause
- **Copyright**: Copyright 2024 Karim Shoair
- **Adapted**: Anti-bot bypass, Cloudflare Turnstile solving, adaptive stealth parsing
- **Modified**: Yes — wrapped as pipeline stage with progressive escalation

## scraper-in-one
- **License**: MIT (provided by browser-goat; original lacked LICENSE)
- **Copyright**: Copyright 2026 Joey Chiu
- **Adapted**: 6-tier progressive escalation pattern, ScrapeRouter architecture
- **Modified**: Yes — wrapped as pipeline stage with progressive escalation
