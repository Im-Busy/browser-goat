"""Multi-angle candidate exploration with adaptive strategy selection.

Generates 4 query variants (direct, synonym, category, related), runs them
via SearXNG in parallel, tracks per-strategy performance, and periodically
re-ranks strategies — removing the worst performer and promoting the best.

Ports the adaptive exploration pattern from local-deep-research's
advanced_search_system/candidate_exploration/adaptive_explorer.py.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from typing import Any

from browsing_meta.models import ExploreResult, StrategyStats

# ── Strategy Names ─────────────────────────────────────────────────────────────

DIRECT = "direct"
SYNONYM = "synonym"
CATEGORY = "category"
RELATED = "related"

ALL_STRATEGIES = [DIRECT, SYNONYM, CATEGORY, RELATED]

# ── Rule-Based Synonym Map ─────────────────────────────────────────────────────
# Simple word-level replacements for the no-LLM fallback.

SYNONYM_MAP: dict[str, list[str]] = {
    "python": ["python programming", "python language", "python coding"],
    "javascript": ["javascript programming", "js", "javascript language"],
    "typescript": ["typescript programming", "ts", "typed javascript"],
    "rust": ["rust programming", "rust language", "rust coding"],
    "go": ["golang", "go programming", "go language"],
    "coding": ["programming", "software development"],
    "tutorial": ["guide", "walkthrough", "how-to"],
    "learn": ["study", "understand", "master"],
    "best": ["top", "leading", "most popular"],
    "tool": ["utility", "software", "framework", "library"],
    "library": ["package", "module", "dependency"],
    "framework": ["platform", "toolkit", "library"],
    "how to": ["guide to", "steps for", "approach for"],
    "setup": ["configure", "install", "get started with"],
    "deploy": ["release", "ship", "publish"],
    "difference": ["comparison", "contrast", "vs"],
    "example": ["sample", "demo", "illustration"],
    "beginner": ["starter", "novice", "getting started"],
    "advanced": ["expert", "pro", "deep dive"],
}

# ── Common Broader Categories (no-LLM fallback) ────────────────────────────────

CATEGORY_MAP: dict[str, str] = {
    "python": "programming languages",
    "javascript": "programming languages",
    "typescript": "programming languages",
    "rust": "programming languages",
    "golang": "programming languages",
    "react": "web frameworks",
    "vue": "web frameworks",
    "angular": "web frameworks",
    "django": "web frameworks",
    "flask": "web frameworks",
    "docker": "containerization tools",
    "kubernetes": "container orchestration",
    "machine learning": "artificial intelligence",
    "deep learning": "artificial intelligence",
    "pytorch": "machine learning frameworks",
    "tensorflow": "machine learning frameworks",
    "postgresql": "relational databases",
    "mongodb": "nosql databases",
    "redis": "in-memory databases",
    "aws": "cloud computing services",
    "azure": "cloud computing services",
    "gcp": "cloud computing services",
}

# ── Common Related Terms (no-LLM fallback) ─────────────────────────────────────

RELATED_MAP: dict[str, list[str]] = {
    "python": ["python vs javascript", "python use cases", "python ecosystem"],
    "javascript": ["javascript vs typescript", "javascript frameworks", "javascript ecosystem"],
    "typescript": ["typescript vs javascript", "typescript best practices"],
    "rust": ["rust vs go", "rust use cases", "rust ecosystem"],
    "docker": ["docker compose", "docker vs podman", "container best practices"],
    "kubernetes": ["kubernetes vs docker swarm", "k8s best practices", "cloud native"],
    "react": ["react vs vue", "react hooks", "react ecosystem"],
    "machine learning": ["ml algorithms", "ml use cases", "ml tools comparison"],
    "aws": ["aws vs azure vs gcp", "aws services overview"],
    "postgresql": ["postgresql vs mysql", "postgresql best practices"],
}

# ── Thresholds ─────────────────────────────────────────────────────────────────

ADAPTATION_THRESHOLD = 5


class AdaptiveExplorer:
    """Multi-angle candidate exploration with adaptive strategy selection.

    Generates 4 query variants from the user's query, runs them all through
    SearXNG concurrently, collects candidate URLs, and tracks per-strategy
    statistics. After enough data accumulates (ADAPTATION_THRESHOLD per
    strategy), strategies are re-ranked by a composite score — the top
    performer is promoted and the bottom performer is dropped.

    The LLM callable must have the signature::

        async def llm_call(messages: list[dict]) -> str

    When no LLM is available **and** no override is provided on ``explore()``,
    falls back to rule-based query generation using built-in synonym,
    category, and related maps. In the no-LLM case only *direct* and *synonym*
    strategies are used; *category* and *related* require LLM support.
    """

    def __init__(
        self,
        llm_call: Callable[[list[dict[str, Any]]], Awaitable[str]] | None = None,
    ) -> None:
        """Initialize the adaptive explorer.

        Args:
            llm_call: Optional async function that takes a list of chat messages
                      and returns a string response. Used for LLM-driven query
                      generation strategies (synonym, category, related).
        """
        self._llm_call = llm_call
        self._stats: dict[str, StrategyStats] = {
            name: StrategyStats(strategy_name=name) for name in ALL_STRATEGIES
        }
        self._strategy_rank: list[str] = ALL_STRATEGIES.copy()

    # ── Public API ─────────────────────────────────────────────────────────────

    async def explore(
        self,
        query: str,
        searxng_client: Any,
        llm_call: Callable[[list[dict[str, Any]]], Awaitable[str]] | None = None,
    ) -> ExploreResult:
        """Execute a multi-angle exploration round.

        Generates up to 4 query variants from the user's query, runs them all
        through SearXNG concurrently via ``asyncio.gather``, collects candidate
        URLs, and updates per-strategy statistics.

        After every strategy has accumulated ADAPTATION_THRESHOLD attempts the
        strategy ranking is re-evaluated — the top scorer is promoted and the
        bottom scorer is dropped from the active set.

        Args:
            query: The user's original search query.
            searxng_client: An instance of ``SearXNGClient`` whose
                ``search(query, ...)`` method returns
                ``list[RawSearchResult]``.
            llm_call: Optional override LLM callable. If ``None``, uses the
                instance-level callable set in ``__init__``. If both are
                ``None``, only *direct* and *synonym* (rule-based) strategies
                are used.

        Returns:
            An ``ExploreResult`` with:
            - **strategy_stats**: per-strategy statistics for this round
            - **candidates**: all candidate URLs found across strategies
            - **total_attempts**: total search attempts across all strategies
            - **adapted_strategy**: the name of the newly promoted top
              strategy if adaptation occurred, otherwise ``None``.
        """
        effective_llm = llm_call or self._llm_call
        has_llm = effective_llm is not None

        # Determine which strategies can produce a variant
        active_strategies = self._active_strategies(has_llm)

        # Generate query variants
        query_variants: dict[str, str] = {}
        for strategy in active_strategies:
            variant = await self._generate_query(
                query=query,
                strategy=strategy,
                has_llm=has_llm,
                llm_call=effective_llm,
            )
            if variant:
                query_variants[strategy] = variant

        # Always ensure at least the direct query is present
        if DIRECT not in query_variants:
            query_variants[DIRECT] = query

        # Execute all variants in parallel via SearXNG
        tasks: dict[str, asyncio.Task[list[str]]] = {
            strategy: asyncio.create_task(
                self._search(strategy, searxng_client, variant),
            )
            for strategy, variant in query_variants.items()
        }

        all_candidates: list[str] = []
        for strategy, task in tasks.items():
            try:
                candidates = await task
                all_candidates.extend(candidates)
            except Exception:
                # Still count the attempt even on failure
                self._stats[strategy].attempts += 1

        stats_list = list(self._stats.values())
        total_attempts = sum(s.attempts for s in stats_list)

        # Adaptation: re-rank if every strategy has enough data
        adapted: str | None = None
        if all(s.attempts >= ADAPTATION_THRESHOLD for s in stats_list):
            adapted = self._adapt()

        return ExploreResult(
            strategy_stats=stats_list,
            candidates=all_candidates,
            total_attempts=total_attempts,
            adapted_strategy=adapted,
        )

    # ── Strategy Selection ─────────────────────────────────────────────────────

    def _active_strategies(self, has_llm: bool) -> list[str]:
        """Return the currently active strategies.

        Without an LLM, only *direct* and *synonym* (rule-based) are
        available — *category* and *related* require LLM generation.
        """
        if has_llm:
            return self._strategy_rank
        return [s for s in self._strategy_rank if s in (DIRECT, SYNONYM)]

    # ── Query Generation ───────────────────────────────────────────────────────

    async def _generate_query(
        self,
        query: str,
        strategy: str,
        has_llm: bool,
        llm_call: Callable[[list[dict[str, Any]]], Awaitable[str]] | None,
    ) -> str | None:
        """Generate a query variant for the given strategy.

        Delegates to the LLM if available and the strategy requires it;
        otherwise falls back to built-in rule-based maps.
        """
        if strategy == DIRECT:
            return query

        if has_llm and llm_call is not None:
            return await self._llm_generate(query, strategy, llm_call)

        return self._rule_generate(query, strategy)

    async def _llm_generate(
        self,
        query: str,
        strategy: str,
        llm_call: Callable[[list[dict[str, Any]]], Awaitable[str]],
    ) -> str | None:
        """Generate a query variant using the LLM.

        Uses a strategy-specific prompt to produce a single alternative query.
        Returns ``None`` if the LLM fails or returns the original query.
        """
        prompts = {
            SYNONYM: (
                f"Rewrite this search query using different words (synonyms). "
                f"Return ONLY the rewritten query, nothing else.\n\n"
                f"Query: {query}"
            ),
            CATEGORY: (
                f"What broader category or superclass does this topic belong to? "
                f"Return ONLY a search query for that broader category, "
                f"nothing else.\n\n"
                f"Query: {query}"
            ),
            RELATED: (
                f"Suggest one closely related but different search query for "
                f"this topic. Return ONLY the related query, nothing else.\n\n"
                f"Query: {query}"
            ),
        }

        prompt = prompts.get(strategy)
        if not prompt:
            return None

        try:
            messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
            response = await llm_call(messages)
            result = response.strip().strip("\"'")
            if result and result.lower() != query.lower():
                return result
        except Exception:
            pass

        return None

    def _rule_generate(self, query: str, strategy: str) -> str | None:
        """Generate a query variant using built-in rule-based maps.

        Supports synonym replacement via ``SYNONYM_MAP``, broader category
        lookup via ``CATEGORY_MAP``, and related term lookup via
        ``RELATED_MAP``.
        """
        query_lower = query.lower()

        if strategy == SYNONYM:
            return self._rule_synonym(query, query_lower)
        if strategy == CATEGORY:
            return self._rule_category(query_lower)
        if strategy == RELATED:
            return self._rule_related(query_lower)

        return None

    def _rule_synonym(self, query: str, query_lower: str) -> str | None:
        """Apply simple word-level synonym replacement.

        Iterates through ``SYNONYM_MAP`` and replaces the first matching
        word with its first synonym alternative. Returns ``None`` if no
        match is found.
        """
        result = query
        replaced = False

        for word, synonyms in SYNONYM_MAP.items():
            if word in query_lower:
                for syn in synonyms:
                    candidate = re.sub(
                        re.escape(word), syn, query, flags=re.IGNORECASE, count=1
                    )
                    if candidate.lower() != query_lower:
                        result = candidate
                        replaced = True
                        break
            if replaced:
                break

        return result if replaced else None

    def _rule_category(self, query_lower: str) -> str | None:
        """Look up a broader category from the built-in map."""
        for keyword, category in CATEGORY_MAP.items():
            if keyword in query_lower:
                return category
        return None

    def _rule_related(self, query_lower: str) -> str | None:
        """Look up a related term from the built-in map."""
        for keyword, terms in RELATED_MAP.items():
            if keyword in query_lower:
                return terms[0]
        return None

    # ── Search Execution ───────────────────────────────────────────────────────

    async def _search(
        self,
        strategy: str,
        searxng_client: Any,
        query: str,
    ) -> list[str]:
        """Execute a search and extract candidate URLs.

        Calls ``searxng_client.search(query=query)``, collects the result
        URLs, and updates the strategy's statistics (attempts, candidates
        found, quality sum). Quality is estimated as the average content
        snippet length across the returned results.

        Args:
            strategy: Strategy name for stats tracking.
            searxng_client: SearXNG client instance.
            query: The query string to search for.

        Returns:
            List of result URLs (candidates) found.
        """
        results = await searxng_client.search(query=query)

        # Collect valid URLs
        urls = [r.url for r in results if r.url]

        # Update per-strategy stats
        stat = self._stats[strategy]
        stat.attempts += 1
        stat.candidates_found += len(urls)

        # Quality estimate: average snippet length as a relevance proxy
        if urls:
            total_content_len = sum(len(r.content) for r in results if r.url)
            stat.quality_sum += total_content_len / max(len(urls), 1)

        return urls

    # ── Strategy Adaptation ─────────────────────────────────────────────────────

    def _adapt(self) -> str:
        """Re-rank strategies based on observed performance.

        Computes a composite score for each strategy:
            ``rate = candidates_found / max(attempts, 1)``
            ``score = rate × (1 + quality_sum / 100)``

        Strategies are sorted descending by score. The top-ranked strategy
        is promoted (returned), and the bottom-ranked strategy is dropped
        from the active set.

        Returns:
            The name of the newly promoted top strategy.
        """
        scored = [
            (name, self._strategy_score(name)) for name in self._strategy_rank
        ]
        scored.sort(key=lambda x: x[1], reverse=True)

        new_rank = [name for name, _score in scored]

        # Drop the bottom performer
        if len(new_rank) > 1:
            new_rank = new_rank[:-1]

        self._strategy_rank = new_rank
        return new_rank[0]

    def _strategy_score(self, name: str) -> float:
        """Compute a composite performance score for a strategy.

        The score balances both the *quantity* of candidates found per
        attempt and the *quality* of those candidates (estimated via snippet
        length). A strategy that finds many rich snippets ranks higher than
        one that finds many empty or sparse results.

        Args:
            name: The strategy name.

        Returns:
            A float score (higher is better). Returns 0.0 if no attempts.
        """
        stat = self._stats[name]
        if stat.attempts == 0:
            return 0.0

        base_rate = stat.candidates_found / stat.attempts
        quality_boost = 1.0 + (stat.quality_sum / 100.0)

        return base_rate * quality_boost

    # ── Public Helpers ─────────────────────────────────────────────────────────

    @property
    def strategy_stats(self) -> dict[str, StrategyStats]:
        """Read-only access to per-strategy statistics."""
        return dict(self._stats)

    @property
    def strategy_rank(self) -> list[str]:
        """Current strategy ranking (best first)."""
        return list(self._strategy_rank)
