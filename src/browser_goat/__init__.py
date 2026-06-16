"""browser-goat — Meta-layer search intelligence wrapping SearXNG.

Layers:
    pre_search   — Query intelligence, language detection, browser profiles
    post_search  — URL pipeline, RRF+BM25+MMR ranking, dedup
    extraction   — Content extraction, goal-oriented, Scrapling anti-bot
    reliability  — Give-up detection, quality gating, force answer
    strategy     — Query classification, adaptive exploration (Phase 2)
    verification — Multi-rollout voting (Phase 3)
"""

from browser_goat.router import BrowserGoat

__version__ = "0.1.0"
__all__ = ["BrowserGoat"]
