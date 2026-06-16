"""N-parallel full-pipeline searches with parameter variation for verification.

Varies browser profiles, engine subsets, and time ranges across rollouts.
Early stops when 4+ identical answers emerge via the answer voter.
"""

from __future__ import annotations

import asyncio
from typing import Any, cast

from browser_goat.models import RolloutConfig, SearchResult
from browser_goat.pre_search.browser_profiles import PROFILES
from browser_goat.verification.answer_voter import AnswerVoter

# ── Variation parameters ──────────────────────────────────────────────────────

_ENGINE_SUBSETS: list[list[str]] = [
    ["google", "bing"],
    ["google", "scholar"],
    ["bing", "scholar"],
]

_TIME_RANGES: list[str | None] = [None, "month", "year"]

# Derived from browser_profiles.PROFILES at runtime for robustness
_NUM_PROFILES: int = len(PROFILES)


class MultiRollout:
    """N-parallel full-pipeline searches with parameter variation.

    Launches multiple config-rolled searches in parallel, checking for
    answer consensus after each completion. Returns all collected results
    so the caller can inspect every rollout alongside the consensus.

    Usage::

        meta = BrowserGoat(searxng_url="http://localhost:8080")
        mr = MultiRollout()
        results = await mr.execute("What happened in the 2024 election?",
                                    meta=meta,
                                    num_rollouts=7)
        # Voting already handled internally; results list contains the
        # completed rollouts up to the early-stop threshold.
    """

    DEFAULT_ROLLOUTS: int = 5
    EARLY_STOP_THRESHOLD: int = 4
    MAX_ROLLOUTS: int = 8

    # ── Config generation ─────────────────────────────────────────────────

    @staticmethod
    def _generate_configs(num_rollouts: int) -> list[RolloutConfig]:
        """Generate *num_rollouts* unique configs over three axes.

        Cycles through three orthogonal variation axes so that every
        rollout is a unique parameter combination:

        * **Browser profile** — round-robin through the 20 profiles
          from ``browser_profiles.PROFILES``.
        * **Engine subset** — ``google+bing``, ``google+scholar``,
          ``bing+scholar``.
        * **Time range** — ``None`` (no filter), ``month``, ``year``.

        The cycling order is: profile first (fastest), then engine,
        then time range (slowest).  This guarantees diverse coverage
        even for small *num_rollouts*.
        """
        profile_names = [p.name for p in PROFILES]
        num_subsets = len(_ENGINE_SUBSETS)
        num_times = len(_TIME_RANGES)

        configs: list[RolloutConfig] = []
        for i in range(num_rollouts):
            profile_name = profile_names[i % _NUM_PROFILES]
            engines = _ENGINE_SUBSETS[(i // _NUM_PROFILES) % num_subsets]
            time_range = _TIME_RANGES[
                (i // (_NUM_PROFILES * num_subsets)) % num_times
            ]

            configs.append(
                RolloutConfig(
                    browser_profile_name=profile_name,
                    engines=engines,
                    time_range=time_range,
                )
            )

        return configs

    # ── Answer extraction ─────────────────────────────────────────────────

    @staticmethod
    def _extract_answer(result: SearchResult) -> str:
        """Extract the plain answer string from a completed ``SearchResult``."""
        return result.answer

    # ── Core execution ────────────────────────────────────────────────────

    async def execute(
        self,
        query: str,
        meta: Any,
        num_rollouts: int = 5,
        answer_voter: AnswerVoter | None = None,
    ) -> list[SearchResult]:
        """Execute *num_rollouts* parallel searches with parameter variation.

        Parameters
        ----------
        query:
            The search query string to pass to every rollout.
        meta:
            A ``BrowserGoat``-like object with an ``async search()`` method.
            Accepted as ``Any`` to **avoid circular imports** — the caller
            passes the concrete instance.
        num_rollouts:
            Number of rollouts to execute (clamped to 1…``MAX_ROLLOUTS``).
        answer_voter:
            Optional ``AnswerVoter`` instance.  When ``None`` (the default)
            a fresh instance is created.

        Returns
        -------
        list[SearchResult]
            All completed rollout results.  When early-stop triggers, only
            the results collected up to that point are returned.  The caller
            can pass these to ``AnswerVoter.vote()`` for the final consensus
            if needed (though the internal voter already checked).

        Notes
        -----
        **Early-stop behaviour**

        After each rollout finishes, the method checks whether at least
        ``EARLY_STOP_THRESHOLD`` (4) answers are identical (per the
        ``AnswerVoter`` similarity grouping).  If so, any remaining in-flight
        rollouts are cancelled and the method returns immediately.

        **Parallelism**

        All rollouts are launched as ``asyncio.Task`` objects immediately.
        Completion is tracked via ``asyncio.wait(FIRST_COMPLETED)`` so that
        we can react to answers as soon as they arrive.
        """
        # Clamp to allowed range
        num_rollouts = min(max(num_rollouts, 1), self.MAX_ROLLOUTS)

        # Generate parameter configurations
        configs = self._generate_configs(num_rollouts)

        # Default voter
        if answer_voter is None:
            answer_voter = AnswerVoter()

        results: list[SearchResult] = []

        # ── Launch all rollouts as parallel tasks ─────────────────────────

        async def _run_one(config: RolloutConfig) -> SearchResult:
            result = await meta.search(
                query=query,
                engines=config.engines,
                time_range=config.time_range,
                language=config.language,
            )
            return cast(SearchResult, result)

        pending: set[asyncio.Task[SearchResult]] = {
            asyncio.create_task(_run_one(c), name=f"rollout-{i}")
            for i, c in enumerate(configs)
        }

        # ── Process completions as they arrive ────────────────────────────

        while pending:
            done, pending = await asyncio.wait(
                pending,
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Collect completed results (skip cancelled tasks)
            for task in done:
                if not task.cancelled():
                    try:
                        result = task.result()
                        results.append(result)
                    except Exception:
                        # Individual rollout failure — skip, continue with
                        # remaining rollouts
                        continue

            # ── Early-stop check ──────────────────────────────────────────
            if len(results) >= self.EARLY_STOP_THRESHOLD:
                answers = [self._extract_answer(r) for r in results]
                vote = answer_voter.vote(answers)
                if vote.consensus and vote.winner_answer is not None:
                    # Consensus reached — cancel remaining tasks
                    for t in pending:
                        t.cancel()
                    break

        return results

