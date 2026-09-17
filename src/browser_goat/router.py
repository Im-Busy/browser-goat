"""BrowserGoat Router — main orchestrator tying all 6 layers together.

Phase 1: Pre-Search → SearXNG → Post-Search → Extraction → Reliability
Phase 2: Strategy dispatch (classify → route to explorer/decomposer/default)
Phase 3: Verification dispatch (standard/high/maximum reliability modes)
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import time
from dataclasses import dataclass
from types import TracebackType
from typing import Any

from browser_goat.cache import TTLFetchCache
from browser_goat.extraction.content_extractor import ContentExtractor
from browser_goat.extraction.goal_oriented import GoalOrientedExtractor
from browser_goat.extraction.response_acceptance import accept_response
from browser_goat.extraction.scrapling_fetcher import ScraplingFetcher
from browser_goat.models import (
    ExtractedSource,
    FetchResult,
    GoalOrientedResult,
    LanguageParams,
    ReliabilityInfo,
    SearchRequest,
    SearchResult,
    VerificationResult,
)
from browser_goat.post_search.ranking import HybridRanker
from browser_goat.post_search.url_pipeline import URLPipeline
from browser_goat.pre_search.browser_profiles import BrowserProfiles
from browser_goat.pre_search.language_detect import (
    detect_language_params,
    get_search_engines_for_language,
)
from browser_goat.pre_search.query_intel import QueryIntel
from browser_goat.reliability.give_up_detector import GiveUpDetector
from browser_goat.reliability.quality_gate import QualityGate
from browser_goat.searxng_client import SearXNGClient
from browser_goat.strategy.adaptive_explorer import AdaptiveExplorer
from browser_goat.strategy.query_classifier import QueryClassifier
from browser_goat.strategy.recursive_decomposer import RecursiveDecomposer
from browser_goat.verification.answer_voter import AnswerVoter
from browser_goat.verification.llm_verifier import LLMVerifier
from browser_goat.verification.multi_rollout import MultiRollout, RolloutProgress

# Maximum concurrent page fetches
MAX_CONCURRENT_FETCHES = 8

# Default content-cache TTL (seconds). Override via CONTENT_CACHE_TTL_SECONDS.
DEFAULT_CACHE_TTL_SECONDS = 900.0
DEFAULT_CACHE_MAX_ENTRIES = 256
MAX_INFLIGHT_FETCHES = 256
VERIFY_MAX_SOURCES = 3


@dataclass
class _PendingFetch:
    task: asyncio.Task[FetchResult]
    waiters: int = 0


class BrowserGoat:
    """Meta-layer search intelligence wrapping SearXNG.

    Usage:
        meta = BrowserGoat(searxng_url="http://localhost:8082")
        result = await meta.search("What is Python?")
        result = await meta.search("Python vs Rust",
                                   strategy="decompose",
                                   reliability_mode="high")
    """

    def __init__(
        self,
        searxng_url: str | None = None,
        llm_call: Any = None,
        cache_ttl_seconds: float | None = None,
        cache_max_entries: int | None = None,
    ) -> None:
        searxng_url = searxng_url or os.environ.get("SEARXNG_URL", "http://localhost:8082")
        self.searxng = SearXNGClient(searxng_url)
        self.query_intel = QueryIntel()
        self.browser_profiles = BrowserProfiles()
        self.url_pipeline = URLPipeline()
        self.ranker = HybridRanker()
        self.content_extractor = ContentExtractor()
        self.goal_extractor = GoalOrientedExtractor(llm_call=llm_call)
        self.scrapling = ScraplingFetcher()
        self.give_up = GiveUpDetector()
        self.quality = QualityGate()
        self._llm_call = llm_call
        self._fetch_semaphore = asyncio.Semaphore(MAX_CONCURRENT_FETCHES)
        self._inflight_fetches: dict[str, _PendingFetch] = {}
        self._inflight_changed = asyncio.Event()
        self._closing = False
        # Phase 2 — Strategy
        self.query_classifier = QueryClassifier(llm_call=llm_call)
        self.adaptive_explorer = AdaptiveExplorer(llm_call=llm_call)
        self.recursive_decomposer = RecursiveDecomposer()
        # Phase 3 — Verification
        self.multi_rollout = MultiRollout()
        self.answer_voter = AnswerVoter()
        self.llm_verifier = LLMVerifier(llm_call=self._verify_llm if llm_call else None)
        # Content-fetch TTL cache (shared across rollouts within this instance)
        ttl = (
            cache_ttl_seconds
            if cache_ttl_seconds is not None
            else float(os.environ.get("CONTENT_CACHE_TTL_SECONDS", DEFAULT_CACHE_TTL_SECONDS))
        )
        max_entries = (
            cache_max_entries
            if cache_max_entries is not None
            else int(os.environ.get("CONTENT_CACHE_MAX_ENTRIES", DEFAULT_CACHE_MAX_ENTRIES))
        )
        self._fetch_cache = TTLFetchCache(ttl_seconds=ttl, max_entries=max_entries)

    async def search(
        self,
        query: str,
        engines: list[str] | None = None,
        time_range: str | None = None,
        language: str = "auto",
        max_sources: int = 15,
        strategy: str = "default",
        reliability_mode: str = "standard",
    ) -> SearchResult:
        """Execute a full search pipeline with optional strategy and verification.

        Args:
            query: The search query.
            engines: Optional list of SearXNG engines to use.
            time_range: Optional time filter (day, week, month, year).
            language: Language code.
            max_sources: Maximum number of sources to extract.
            strategy: "default" (existing pipeline), "auto" (classify→route),
                      "explore" (adaptive multi-angle), "decompose" (recursive).
            reliability_mode: "standard" (single pass), "high" (5 rollouts+voting),
                              "maximum" (8 rollouts+voting+LLM verify), "auto".

        Returns:
            SearchResult with sources, query analysis, and metrics.
        """
        SearchRequest.model_validate({"query": query, "engines": engines, "time_range": time_range,
                                      "language": language, "max_sources": max_sources, "strategy": strategy,
                                      "reliability_mode": reliability_mode})
        # ── Phase 3: Verification dispatch ────────────────────────────────
        if reliability_mode in ("high", "maximum"):
            return await self._verified_search(
                query, engines, time_range, language, max_sources,
                strategy, reliability_mode,
            )
        elif reliability_mode == "auto":
            analysis = self.query_intel.analyze(query)
            if (
                analysis.intent in ("research", "comparison")
                and analysis.complexity == "complex"
            ):
                return await self._verified_search(
                    query, engines, time_range, language, max_sources,
                    strategy, "high",
                )

        # ── Phase 2: Strategy dispatch ─────────────────────────────────────
        if strategy == "auto":
            classification = await self.query_classifier.classify(query)
            if classification.query_type == "research":
                strategy = "explore"
            elif classification.complexity == "complex" or classification.query_type == "puzzle":
                strategy = "decompose"
            else:
                strategy = "default"

        if strategy == "explore":
            return await self._explore_search(
                query, engines, time_range, language, max_sources,
            )
        elif strategy == "decompose":
            return await self._decompose_search(
                query, engines, time_range, language, max_sources,
            )

        # ── Default pipeline (Phase 1) ─────────────────────────────────────
        return await self._default_search(
            query, engines, time_range, language, max_sources,
        )

    # ── Default Pipeline ───────────────────────────────────────────────────

    async def _default_search(
        self,
        query: str,
        engines: list[str] | None,
        time_range: str | None,
        language: str,
        max_sources: int,
    ) -> SearchResult:
        """Phase 1 default pipeline: Pre-Search → SearXNG → Post-Search → Extraction → Reliability."""
        start = time.monotonic()

        analysis = self.query_intel.analyze(query)
        lang_params = self._language_params(query, language)
        profile = self.browser_profiles.get_random_profile()
        enriched_query = self.query_intel.enrich_query(query, analysis)

        if engines is None:
            engines = get_search_engines_for_language(lang_params)

        raw_results = await self.searxng.search(
            enriched_query,
            engines=engines,
            language=lang_params.hl,
            time_range=time_range,
            browser_profile=profile,
            lang_params=lang_params,
        )

        total_found = len(raw_results)
        cleaned = self.url_pipeline.process(raw_results)
        ranked = self.ranker.rank(cleaned, query, max_results=max_sources)

        sources, successful, extraction_success_rate = await self._extract_sources(
            ranked, query, profile,
        )

        answer = self._build_basic_answer(query, sources)
        reliability = self._run_reliability(answer, sources)

        latency = int((time.monotonic() - start) * 1000)
        return SearchResult(
            answer=answer,
            sources=sources,
            query_intent=analysis.intent,
            engines_used=engines,
            total_sources_found=total_found,
            total_sources_used=len(successful),
            extraction_success_rate=extraction_success_rate,
            pipeline_latency_ms=latency,
            reliability=reliability,
        )

    # ── Phase 2: Strategy Dispatchers ──────────────────────────────────────

    async def _explore_search(
        self,
        query: str,
        engines: list[str] | None,
        time_range: str | None,
        language: str,
        max_sources: int,
    ) -> SearchResult:
        """Adaptive multi-angle exploration via AdaptiveExplorer."""
        start = time.monotonic()

        analysis = self.query_intel.analyze(query)
        lang_params = self._language_params(query, language)
        profile = self.browser_profiles.get_random_profile()

        if engines is None:
            engines = get_search_engines_for_language(lang_params)

        explore_result = await self.adaptive_explorer.explore(
            query, self.searxng,
            search_options={"engines": engines, "language": lang_params.hl, "time_range": time_range,
                            "browser_profile": profile, "lang_params": lang_params},
        )
        raw_results = explore_result.results
        total_found = len(raw_results)

        cleaned = self.url_pipeline.process(raw_results)
        ranked = self.ranker.rank(cleaned, query, max_results=max_sources)

        sources, successful, extraction_success_rate = await self._extract_sources(
            ranked, query, profile,
        )

        answer = self._build_basic_answer(query, sources)
        reliability = self._run_reliability(answer, sources)

        latency = int((time.monotonic() - start) * 1000)
        return SearchResult(
            answer=answer,
            sources=sources,
            query_intent=analysis.intent,
            engines_used=engines,
            total_sources_found=total_found,
            total_sources_used=len(successful),
            extraction_success_rate=extraction_success_rate,
            pipeline_latency_ms=latency,
            reliability=reliability,
        )

    async def _decompose_search(
        self,
        query: str,
        engines: list[str] | None,
        time_range: str | None,
        language: str,
        max_sources: int,
    ) -> SearchResult:
        """Recursive decomposition via RecursiveDecomposer."""
        if self._llm_call is None:
            # Explicitly documented no-LLM fallback; never pretend to decompose.
            return await self._default_search(query, engines, time_range, language, max_sources)
        start = time.monotonic()

        analysis = self.query_intel.analyze(query)
        lang_params = self._language_params(query, language)
        profile = self.browser_profiles.get_random_profile()

        if engines is None:
            engines = get_search_engines_for_language(lang_params)

        decomposed = await self.recursive_decomposer.decompose_and_solve(
            query, self.searxng, self._llm_call,
            search_options={"engines": engines, "language": lang_params.hl, "time_range": time_range,
                            "browser_profile": profile, "lang_params": lang_params},
        )
        raw_results = decomposed.results
        total_found = len(raw_results)

        cleaned = self.url_pipeline.process(raw_results)
        ranked = self.ranker.rank(cleaned, query, max_results=max_sources)

        sources, successful, extraction_success_rate = await self._extract_sources(
            ranked, query, profile,
        )

        answer = decomposed.aggregated_answer or self._build_basic_answer(query, sources)
        reliability = self._run_reliability(answer, sources)

        latency = int((time.monotonic() - start) * 1000)
        return SearchResult(
            answer=answer,
            sources=sources,
            query_intent=analysis.intent,
            engines_used=engines,
            total_sources_found=total_found,
            total_sources_used=len(successful),
            extraction_success_rate=extraction_success_rate,
            pipeline_latency_ms=latency,
            reliability=reliability,
        )

    # ── Phase 3: Verification ──────────────────────────────────────────────

    async def _verified_search(
        self,
        query: str,
        engines: list[str] | None,
        time_range: str | None,
        language: str,
        max_sources: int,
        strategy: str,
        reliability_mode: str,
    ) -> SearchResult:
        """Multi-rollout verified search with consensus voting."""
        rollout_count = 8 if reliability_mode == "maximum" else 5
        result, _ = await self._verify(
            query, rollout_count,
            {"engines": engines, "time_range": time_range, "language": language,
             "max_sources": max_sources, "strategy": strategy},
        )
        return result

    async def verify(self, query: str, rollouts: int = 5) -> dict[str, Any]:
        """Verify a query with 3-8 rollouts and return vote details."""
        SearchRequest(query=query)
        if isinstance(rollouts, bool) or not isinstance(rollouts, int) or not 3 <= rollouts <= 8:
            raise ValueError("rollouts must be an integer from 3 to 8")
        result, votes = await self._verify(query, rollouts, {"max_sources": VERIFY_MAX_SOURCES})
        return {**result.model_dump(mode="json"), "query": query, **votes}

    async def _verify(
        self, query: str, rollouts: int, search_options: dict[str, Any] | None = None,
    ) -> tuple[SearchResult, dict[str, Any]]:
        start = time.monotonic()
        budget = self.multi_rollout.COLLECTION_TIMEOUT_SECONDS
        progress = RolloutProgress()
        options = dict(search_options or {})
        if options.get("engines") is None:
            options.pop("engines", None)
        results = await self.multi_rollout.execute(
            query=query, meta=self, num_rollouts=rollouts, answer_voter=self.answer_voter,
            search_options=options, timeout_seconds=budget, progress=progress,
        )
        collection = {
            "requested_rollouts": rollouts, "failed_rollouts": progress.failed_rollouts,
            "cancelled_rollouts": progress.cancelled_rollouts, "timed_out": progress.timed_out,
            "partial": len(results) < rollouts, "stop_reason": progress.stop_reason,
            "timeout_seconds": budget,
        }
        valid = [r for r in results if r.answer.strip() and r.reliability.quality_passed
                 and not r.reliability.give_up_detected]
        vote = self.answer_voter.vote([r.answer for r in valid])
        details = {"rollouts_run": len(results), "vote_counts": vote.vote_counts, "candidates": vote.candidates}
        if not valid:
            answer = (
                "Verification timed out before any usable rollout completed."
                if progress.timed_out else
                "No usable results from verification rollouts. Check SearXNG and extraction."
            )
            return SearchResult(
                answer=answer, reliability=ReliabilityInfo(quality_passed=False),
                pipeline_latency_ms=int((time.monotonic() - start) * 1000),
                verification=VerificationResult(selected_answer=answer, method="rollout_failure",
                                                rollout_count=len(results)).model_copy(update=collection),
            ), details
        chosen = vote.winner_answer or vote.candidates[0]
        verification = VerificationResult(
            selected_answer=chosen, confidence=vote.confidence,
            method="consensus" if vote.consensus else "fallback",
            is_consensus=vote.consensus, rollout_count=len(results),
        )
        if rollouts > 5 and len(vote.candidates) > 1:
            remaining = max(0.0, budget - (time.monotonic() - start))
            if remaining and not progress.timed_out:
                try:
                    verification = await asyncio.wait_for(
                        self.llm_verifier.verify(
                            query=query, candidates=vote.candidates,
                            sources=[src for result in valid for src in result.sources][:10],
                        ), timeout=remaining,
                    )
                    verification.rollout_count = len(results)
                    chosen = verification.selected_answer
                except TimeoutError:
                    collection.update(timed_out=True, stop_reason="verifier_timeout")
                    verification.reasoning = "Verifier exceeded the remaining budget; retained voted fallback."
            elif not progress.timed_out:
                collection.update(timed_out=True, stop_reason="verifier_timeout")
        verification = verification.model_copy(update=collection)
        selected = next(r for r in valid if r.answer == chosen)
        result = selected.model_copy(update={
            "answer": chosen, "verification": verification,
            "pipeline_latency_ms": int((time.monotonic() - start) * 1000),
        })
        return result, details

    # ── Shared Extraction ─────────────────────────────────────────────────

    async def _extract_sources(
        self,
        ranked: list[Any],
        query: str,
        profile: Any,
    ) -> tuple[list[ExtractedSource], list[Any], float]:
        """Extract content from ranked results. Returns (sources, successful, rate).

        Preserves the original rank index by zipping each task with its
        source position in ``ranked``.  Previously this used
        ``ranked.index(ranked_result)`` inside the comprehension, which is
        O(N²) and silently mis-indexes when the same URL appears more than
        once.
        """
        # Each fetch task is tagged with its original rank index so the
        # success loop can recover the matched RankedResult without a
        # reverse lookup.
        async def fetch_and_extract(
            index: int, ranked_result: Any,
        ) -> tuple[int, GoalOrientedResult | None, FetchResult | None]:
            fetch_result: FetchResult | None = None
            try:
                fetch_result = await self._fetch_with_cache(
                    ranked_result.url, profile,
                )
                if not fetch_result.success:
                    return index, None, fetch_result
                extracted = self.content_extractor.extract(
                    fetch_result.html, ranked_result.url,
                )
                if not extracted.text:
                    return index, None, fetch_result
                result = await self.goal_extractor.extract(extracted, query)
                return index, result, fetch_result
            except Exception:
                return index, None, fetch_result

        tasks = [
            asyncio.create_task(fetch_and_extract(i, r))
            for i, r in enumerate(ranked)
        ]
        try:
            tagged_results = await asyncio.gather(*tasks)
        finally:
            # A rollout deadline must drain children, including shielded shared
            # fetch cleanup, before returning partial verification metadata.
            for task in tasks:
                if not task.done() and not task.cancelling():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        # Walk in original rank order so the final ``ExtractedSource.rank``
        # mirrors the ranking pipeline output.
        successful = [r for _, r, _ in tagged_results if r is not None]
        extraction_success_rate = (
            len(successful) / len(ranked) if ranked else 0.0
        )

        sources: list[ExtractedSource] = []
        for original_index, result, fetch_result in tagged_results:
            if result is None:
                continue
            ranked_result = ranked[original_index]
            used_scrapling = bool(
                fetch_result is not None
                and (
                    getattr(fetch_result, "used_scrapling", False)
                    or getattr(fetch_result, "used_crawl4ai", False)
                )
            )
            sources.append(
                ExtractedSource(
                    url=result.url,
                    title=result.title,
                    rational=result.rational,
                    evidence=result.evidence,
                    summary=result.summary,
                    extraction_tier=result.extraction_tier,
                    used_scrapling=used_scrapling,
                    rank=original_index + 1,
                    final_score=ranked_result.final_score,
                    engine=ranked_result.engine,
                )
            )

        return sources, successful, extraction_success_rate

    async def _fetch_with_cache(
        self, url: str, profile: Any,
    ) -> FetchResult:
        """Share in-flight URL fetches; cancellation affects only the last waiter.

        Track at most MAX_INFLIGHT_FETCHES URLs, with backpressure for new URLs.
        Successes enter the TTL cache; failures are shared only by current
        waiters so a later call can retry. Completed entries are always removed.
        """
        while True:
            if self._closing:
                raise RuntimeError("BrowserGoat is closed")
            cached_html = self._fetch_cache.get(url)
            if cached_html is not None:
                return FetchResult(url=url, html=cached_html, status_code=200, success=True)
            pending = self._inflight_fetches.get(url)
            if pending is not None:
                if pending.waiters == 0:
                    # Last consumer is draining cancellation/completion. A new
                    # caller must not attach to that retired operation.
                    self._inflight_changed.clear()
                    await self._inflight_changed.wait()
                    continue
                break
            if len(self._inflight_fetches) < MAX_INFLIGHT_FETCHES:
                pending = _PendingFetch(asyncio.create_task(self._fetch_and_cache(url, profile)))
                self._inflight_fetches[url] = pending
                break
            self._inflight_changed.clear()
            await self._inflight_changed.wait()
        pending.waiters += 1
        try:
            return await asyncio.shield(pending.task)
        finally:
            pending.waiters -= 1
            if pending.waiters == 0:
                # Keep the slot until cancelled network work has actually drained.
                try:
                    if not pending.task.done():
                        pending.task.cancel()
                    await asyncio.gather(pending.task, return_exceptions=True)
                finally:
                    if self._inflight_fetches.get(url) is pending:
                        del self._inflight_fetches[url]
                    self._inflight_changed.set()

    async def _fetch_and_cache(self, url: str, profile: Any) -> FetchResult:
        """Run the single fetch shared by waiters, bounded by the instance semaphore."""
        async with self._fetch_semaphore:
            cached_html = self._fetch_cache.get(url)
            if cached_html is not None:
                return FetchResult(url=url, html=cached_html, status_code=200, success=True)
            fetch_result = accept_response(await self.scrapling.fetch(url, browser_profile=profile))
        if fetch_result.success and fetch_result.html:
            with contextlib.suppress(Exception):
                # Cache write failure must never break a fetch
                self._fetch_cache.put(url, fetch_result.html)
        return fetch_result

    def _build_basic_answer(
        self, query: str, sources: list[ExtractedSource],
    ) -> str:
        """Build a basic answer from extracted sources (no LLM)."""
        if not sources:
            return (
                f"No relevant information found for: {query}. "
                "Try rephrasing or broadening the search."
            )
        parts: list[str] = [f"Results for: {query}\n"]
        for i, source in enumerate(sources[:5], 1):
            parts.append(f"[{i}] {source.title} ({source.url})")
            if source.summary:
                parts.append(f"    {source.summary[:200]}")
        return "\n".join(parts)

    def _run_reliability(
        self, answer: str, sources: list[ExtractedSource],
    ) -> ReliabilityInfo:
        """Run reliability checks on a synthesized answer."""
        reliability = ReliabilityInfo()
        give_up = self.give_up.detect(answer)
        reliability.give_up_detected = give_up.detected
        reliability.give_up_pattern = give_up.pattern_matched
        quality = self.quality.check(answer, sources)
        reliability.quality_passed = quality.passed and bool(sources) and not give_up.detected
        reliability.quality_retries = quality.retries_used
        # No synthesis/retry is performed here; do not report a discarded prompt as used.
        return reliability

    @staticmethod
    def _language_params(query: str, language: str) -> LanguageParams:
        params = detect_language_params(query)
        if language != "auto":
            params.hl = language
        return params

    async def _verify_llm(self, prompt: str) -> str:
        """Adapt the public chat-message callable to the verifier's prompt callable."""
        return str(await self._llm_call([{"role": "user", "content": prompt}]))

    async def __aenter__(self) -> BrowserGoat:
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        """Close all HTTP clients."""
        self._closing = True
        tasks = [pending.task for pending in self._inflight_fetches.values()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._inflight_fetches.clear()
        self._inflight_changed.set()
        await self.searxng.close()
        await self.scrapling.close()

    async def extract(self, url: str) -> dict[str, Any]:
        """Fetch one URL, returning full text or an explicit extraction failure."""
        profile = self.browser_profiles.get_random_profile()
        fetch = await self._fetch_with_cache(url, profile)
        if not fetch.success:
            return {"url": url, "success": False, "error": fetch.error or "fetch failed"}
        content = self.content_extractor.extract(fetch.html, url)
        return {"url": url, "title": content.title, "text": content.text,
                "extraction_tier": content.extraction_tier, "text_length": len(content.text),
                "success": bool(content.text), "error": None if content.text else "No extractable text"}

    def cache_stats(self) -> dict[str, Any]:
        """Return observability counters for the content-fetch TTL cache."""
        return self._fetch_cache.stats()

    def clear_cache(self) -> None:
        """Clear the content-fetch TTL cache and reset counters."""
        self._fetch_cache.clear()
