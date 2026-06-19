# Phase 3 — Verification & Scaling Plan

> **Status**: ⏳ Pending | **Target**: Multi-rollout verification for high-stakes queries
> **Depends On**: Phase 2 (Strategy Intelligence) must be complete
> **Estimated Effort**: 5-7 days (single developer)

---

## Overview

Phase 3 adds the Verification Layer (Layer 6), making browser-goat reliable for high-stakes queries where correctness matters more than speed. It runs multiple search rollouts with variation, votes on answers, and uses an LLM verifier for consensus.

**All patterns ported from Marco-DeepResearch.**

---

## What Phase 3 Adds

```
Phase 2:  classify → route → search → rank → extract → answer
Phase 3:  classify → route → ┌─ rollout_1 (Chrome profile A, engines X,Y) ─┐
                              ├─ rollout_2 (Firefox profile B, engines Y,Z)─┤
                              ├─ rollout_3 (Safari profile C, engines X,Z) ─┤
                              └─ rollout_N (Edge profile D, engines A,B)  ─┘
                              │
                              ▼
                          vote → verify → final answer
```

---

## Task Breakdown

### Task 3.1 — Multi-Rollout (`verification/multi_rollout.py`)
**Source**: `Marco-DeepResearch/marco/agent/context_manager.py:254-328`
**Effort**: 4 hours

```python
class MultiRollout:
    """
    Run N parallel searches with different parameters to get varied results.
    Variation axes: browser profile, engine selection, time range, language.
    """
    
    DEFAULT_ROLLOUTS = 5
    EARLY_STOP_THRESHOLD = 4  # Stop if same answer appears 4+ times
    MAX_ROLLOUTS = 8
    
    async def execute(
        self, query: str, meta: BrowserGoat, num_rollouts: int = DEFAULT_ROLLOUTS
    ) -> list[SearchResult]:
        """Run N parallel searches with parameter variation."""
        
        # Generate N varied parameter sets:
        # - Different browser profile per rollout
        # - Different engine subsets (google+bing vs google+scholar vs bing+scholar)
        # - Different time ranges (year vs month vs none)
        # - Different languages (en vs all)
        
        # Execute all in parallel via asyncio.gather()
        # Early stop: if same answer appears 4+ times, cancel remaining
        
        return results
```

Key design:
- Vary parameters across rollouts to get genuinely different results, not just re-requests
- Early stop saves API calls when consensus is strong
- Each rollout is a full Phase 1+2 pipeline call

### Task 3.2 — Answer Voter (`verification/answer_voter.py`)
**Source**: `Marco-DeepResearch/marco/agent/context_manager.py:274-284`
**Effort**: 3 hours

```python
class AnswerVoter:
    """
    Collect answers from multiple rollouts, vote for consensus.
    """
    
    def vote(self, results: list[SearchResult]) -> VoteResult:
        """Count identical/similar answers across rollouts."""
        
        # Step 1: Normalize answers (lowercase, strip whitespace, remove citation numbers)
        # Step 2: Group by normalized text
        # Step 3: Count votes per group
        # Step 4: Determine winner
        
        if winner.votes >= 4:
            return VoteResult(consensus=True, answer=winner.answer, confidence=HIGH)
        elif winner.votes > others:
            return VoteResult(consensus=True, answer=winner.answer, confidence=MEDIUM)
        else:
            return VoteResult(consensus=False, candidates=tied_answers)
```

Similarity detection: answers with >85% normalized text overlap are considered "the same answer."

### Task 3.3 — LLM Verifier (`verification/llm_verifier.py`)
**Source**: `Marco-DeepResearch/marco/agent/context_manager.py:286-328`
**Effort**: 3 hours

```python
class LLMVerifier:
    """
    When voting ties or confidence is low, use an LLM to evaluate competing answers.
    """
    
    async def verify(
        self, query: str, candidates: list[str], sources: list[list[ExtractedSource]], llm_config: dict
    ) -> VerificationResult:
        """LLM evaluates which candidate answer is most correct."""
        
        # Prompt: "Here are N different answers to the same query.
        # For each answer, check: factual accuracy, source support, completeness.
        # Select the best answer or synthesize a combined answer."
        
        # Returns: selected answer + confidence score + reasoning
```

### Task 3.4 — Reliability Mode Integration
**Effort**: 3 hours

Add a `reliability_mode` to `BrowserGoat.search()`:

```python
class BrowserGoat:
    async def search(
        self, 
        query: str, 
        reliability_mode: str = "standard"  # "standard" | "high" | "maximum"
    ) -> SearchResult:
        
        if reliability_mode == "standard":
            # Phase 1+2: single pass
            return await self._standard_search(query)
        
        elif reliability_mode == "high":
            # Phase 1+2+3: 5 rollouts with voting
            results = await self.multi_rollout.execute(query, self, num_rollouts=5)
            vote = self.answer_voter.vote(results)
            if vote.consensus:
                return vote.to_search_result()
            else:
                return await self.llm_verifier.verify(query, vote.candidates, ...)
        
        elif reliability_mode == "maximum":
            # Phase 1+2+3: 8 rollouts with voting + LLM verify always
            results = await self.multi_rollout.execute(query, self, num_rollouts=8)
            vote = self.answer_voter.vote(results)
            return await self.llm_verifier.verify(query, vote.candidates, ...)
```

### Task 3.5 — Automatic Mode Selection
**Effort**: 2 hours

Auto-select reliability mode based on query classification:

```python
RELIABILITY_MODE_MAP = {
    "FACTUAL": "standard",     # "What is X?" — simple lookup, low stakes
    "TEMPORAL": "standard",    # "Latest X?" — speed matters more
    "PERSON": "standard",      # "Who is X?" — usually unambiguous
    "COMPARISON": "high",      # "X vs Y" — opinion affects answers
    "HOWTO": "standard",       # "How to X?" — multiple valid answers
    "RESEARCH": "high",        # Open-ended — quality matters
    "PUZZLE": "maximum",       # Multi-step — correctness is critical
}
```

### Task 3.6 — Tests
**Effort**: 4 hours

- Test multi-rollout parameter variation (verify unique profiles)
- Test early stop logic (simulate 4 identical answers)
- Test voter with identical, similar, and different answers
- Test LLM verifier with known correct/incorrect answer pairs
- Integration: RESEARCH query in "high" mode produces verified answer

---

## Phase 3 Completion Criteria

- [ ] Multi-rollout runs N parallel searches with varied parameters
- [ ] Early stop triggers at 4+ identical answers
- [ ] Answer voter detects consensus and returns confidence level
- [ ] LLM verifier correctly selects best answer from tied candidates
- [ ] Reliability mode dispatches correctly: standard/high/maximum
- [ ] Auto-selection maps query types to appropriate modes
- [ ] All tests pass, typecheck clean
- [ ] High-reliability queries produce demonstrably more accurate answers than standard

---

## Cost Implications

Multi-rollout verification increases API costs N× per query. This is intentional — verification is for high-stakes queries only.

| Mode | Rollouts | Cost Multiplier | Use Case |
|------|----------|----------------|---------|
| `standard` | 1 | 1× | Default for simple queries |
| `high` | 5 | 5× (or less with early stop) | Research and comparison queries |
| `maximum` | 8 | 8× (or less with early stop) | Puzzle/multi-step queries |

**Early stop saves cost**: If consensus is reached at rollout 4, the remaining 1-4 rollouts are cancelled.

---

## Future: Phase 3+ Ideas (Deferred)

| Idea | Source | What It Does |
|------|--------|-------------|
| **ReSum conversation compression** | Tongyi ReSum | Periodically compress agent conversation to extend search chains |
| **Table-as-Search hierarchical agents** | Marco Table-as-Search | Separate wide/explore agent from deep/extract agent |
| **WebWeaver dynamic outlines** | Tongyi WebWeaver | Interleave search with evolving outline for report generation |
| **UMEM self-evolving memory** | Marco UMEM | Learn which search patterns work best over time |
