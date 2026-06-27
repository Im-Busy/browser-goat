"""BrowserGoat Router — main orchestrator tying all 6 layers together.

Phase 1: Pre-Search → SearXNG → Post-Search → Extraction → Reliability
Phase 2: Strategy dispatch (classify → route to explorer/decomposer/default)
Phase 3: Verification dispatch (standard/high/maximum reliability modes)
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from browser_goat.extraction.content_extractor import ContentExtractor
from browser_goat.extraction.goal_oriented import GoalOrientedExtractor
from browser_goat.extraction.scrapling_fetcher import ScraplingFetcher
from browser_goat.models import (
    ExtractedSource,
    GoalOrientedResult,
    ReliabilityInfo,
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
from browser_goat.reliability.force_answer import (
    build_force_answer_prompt,
    format_sources_for_prompt,
)
from browser_goat.reliability.give_up_detector import GiveUpDetector
from browser_goat.reliability.quality_gate import QualityGate
from browser_goat.searxng_client import SearXNGClient
from browser_goat.strategy.adaptive_explorer import AdaptiveExplorer
from browser_goat.strategy.query_classifier import QueryClassifier
from browser_goat.strategy.recursive_decomposer import RecursiveDecomposer
from browser_goat.verification.answer_voter import AnswerVoter
from browser_goat.verification.llm_verifier import LLMVerifier
from browser_goat.verification.multi_rollout import MultiRollout

# Maximum concurrent page fetches
MAX_CONCURRENT_FETCHES = 8


class BrowserGoat:
    """Meta-layer search intelligence wrapping SearXNG.

    Usage:
        meta = BrowserGoat(searxng_url="http://localhost:8080")
        result = await meta.search("What is Python?")
        result = await meta.search("Python vs Rust",
                                   strategy="decompose",
                                   reliability_mode="high")
    """

    def __init__(
        self,
        searxng_url: str = "http://localhost:8080",
        llm_call: Any = None,
    ) -> None:
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
        # Phase 2 — Strategy
        self.query_classifier = QueryClassifier()
        self.adaptive_explorer = AdaptiveExplorer()
        self.recursive_decomposer = RecursiveDecomposer()
        # Phase 3 — Verification
        self.multi_rollout = MultiRollout()
        self.answer_voter = AnswerVoter()
        self.llm_verifier = LLMVerifier(llm_call=llm_call)

    async def search(
        self,
        query: str,
        engines: list[str] | None = None,
        time_range: str | None = None,
        language: str = "en",
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
        lang_params = detect_language_params(query)
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
        lang_params = detect_language_params(query)
        profile = self.browser_profiles.get_random_profile()

        if engines is None:
            engines = get_search_engines_for_language(lang_params)

        explore_result = await self.adaptive_explorer.explore(
            query, self.searxng,
        )

        merged_query = query
        total_found = len(explore_result.candidates)

        raw_results = await self.searxng.search(
            merged_query,
            engines=engines,
            language=lang_params.hl,
            time_range=time_range,
            browser_profile=profile,
            lang_params=lang_params,
        )

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
        start = time.monotonic()

        analysis = self.query_intel.analyze(query)
        lang_params = detect_language_params(query)
        profile = self.browser_profiles.get_random_profile()

        if engines is None:
            engines = get_search_engines_for_language(lang_params)

        raw_results = await self.searxng.search(
            query,
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

        results = await self.multi_rollout.execute(
            query=query,
            meta=self,
            num_rollouts=rollout_count,
            answer_voter=self.answer_voter,
        )

        if not results:
            return SearchResult(
                answer="No results from verification rollouts.",
                verification=VerificationResult(
                    selected_answer="No results from verification rollouts.",
                    confidence=None,
                    method="rollout_failure",
                    is_consensus=False,
                    rollout_count=0,
                ),
            )

        answers = [r.answer for r in results]
        vote = self.answer_voter.vote(answers)

        if vote.consensus and vote.winner_answer:
            return SearchResult(
                answer=vote.winner_answer,
                sources=results[0].sources if results else [],
                query_intent=results[0].query_intent if results else results[0].query_intent,
                engines_used=results[0].engines_used if results else [],
                total_sources_found=sum(r.total_sources_found for r in results),
                total_sources_used=sum(r.total_sources_used for r in results),
                extraction_success_rate=(
                    sum(r.extraction_success_rate for r in results) / len(results)
                    if results else 0.0
                ),
                pipeline_latency_ms=results[0].pipeline_latency_ms if results else 0,
                verification=VerificationResult(
                    selected_answer=vote.winner_answer,
                    confidence=vote.confidence,
                    method="consensus",
                    is_consensus=True,
                    rollout_count=rollout_count,
                ),
            )

        if reliability_mode == "maximum" and len(vote.candidates) > 1:
            all_sources = [src for r in results for src in r.sources]
            verification = await self.llm_verifier.verify(
                query=query,
                candidates=vote.candidates,
                sources=all_sources[:10],
            )
            return SearchResult(
                answer=verification.selected_answer,
                sources=results[0].sources if results else [],
                verification=VerificationResult(
                    selected_answer=verification.selected_answer,
                    confidence=verification.confidence,
                    method="llm",
                    is_consensus=False,
                    rollout_count=rollout_count,
                ),
            )

        return SearchResult(
            answer=vote.candidates[0] if vote.candidates else "No consensus reached.",
            sources=results[0].sources if results else [],
            verification=VerificationResult(
                selected_answer=vote.candidates[0] if vote.candidates else "No consensus reached.",
                confidence=None,
                method="fallback",
                is_consensus=False,
                rollout_count=rollout_count,
            ),
        )

    # ── Shared Extraction ─────────────────────────────────────────────────

    async def _extract_sources(
        self,
        ranked: list[Any],
        query: str,
        profile: Any,
    ) -> tuple[list[ExtractedSource], list[Any], float]:
        """Extract content from ranked results. Returns (sources, successful, rate)."""
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_FETCHES)

        async def fetch_and_extract(ranked_result: Any) -> GoalOrientedResult | None:
            async with semaphore:
                fetch_result = await self.scrapling.fetch(
                    ranked_result.url,
                    browser_profile=profile,
                )
                if not fetch_result.success:
                    return None
                extracted = self.content_extractor.extract(
                    fetch_result.html, ranked_result.url,
                )
                if not extracted.text:
                    return None
                return await self.goal_extractor.extract(extracted, query)

        tasks = [fetch_and_extract(r) for r in ranked]
        extracted_results = await asyncio.gather(*tasks)

        successful = [r for r in extracted_results if r is not None]
        extraction_success_rate = len(successful) / len(ranked) if ranked else 0.0

        sources: list[ExtractedSource] = []
        for i, result in enumerate(successful):
            ranked_result = ranked[i] if i < len(ranked) else None
            sources.append(
                ExtractedSource(
                    url=result.url,
                    title=result.title,
                    rational=result.rational,
                    evidence=result.evidence,
                    summary=result.summary,
                    extraction_tier=result.extraction_tier,
                    used_scrapling=(
                        getattr(extracted_results[ranked.index(ranked_result)], "used_scrapling", False)
                        if ranked_result and ranked_result in ranked
                        else False
                    ),
                    rank=i + 1,
                    final_score=ranked_result.final_score if ranked_result else 0.0,
                    engine=ranked_result.engine if ranked_result else "",
                )
            )

        return sources, successful, extraction_success_rate

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
        reliability.quality_passed = quality.passed
        reliability.quality_retries = quality.retries_used
        if give_up.detected or not quality.passed:
            build_force_answer_prompt(query="", sources_text=format_sources_for_prompt(sources))
            reliability.force_answer_used = True
        return reliability

    async def close(self) -> None:
        """Close all HTTP clients."""
        await self.searxng.close()
        await self.scrapling.close()
