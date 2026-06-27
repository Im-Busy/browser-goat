# Phase 2 — Strategy Intelligence Plan

> **Status**: ✅ Complete | **Target**: Smart query routing and adaptive exploration
> **Depends On**: Phase 1 (Core Pipeline) must be complete and working
> **Estimated Effort**: 5-7 days (single developer)

---

## Overview

Phase 2 adds the Strategy Layer (Layer 5), making browser-goat "smart" instead of just "fast." The core pipeline (Phase 1) treats every query the same way. Phase 2 classifies queries and applies different strategies based on query type, generating multiple search angles and recursively decomposing complex questions.

**All patterns ported from local-deep-research.**

---

## What Phase 2 Adds

```
Phase 1:  query → SearXNG → rank → extract → answer    (same path for everything)
Phase 2:  query → classify → route to strategy → SearXNG → rank → extract → answer
                         │
                         ├── FACTUAL → direct search
                         ├── TEMPORAL → news-boosted search  
                         ├── COMPARISON → side-by-side searches
                         ├── HOWTO → tutorial-focused search
                         ├── RESEARCH → multi-angle exploration
                         └── COMPLEX → recursive decomposition
```

---

## Task Breakdown

### Task 2.1 — Query Classifier (`strategy/query_classifier.py`)
**Source**: `local-deep-research/strategies/smart_decomposition_strategy.py`
**Effort**: 3 hours

```python
class QueryClassifier:
    """LLM-powered query classification and strategy routing."""
    
    QUERY_TYPES = [
        "FACTUAL",        # Simple lookup: "What is X?"
        "TEMPORAL",       # Time-sensitive: "Latest X?"
        "PERSON",         # Person lookup: "Who is X?"
        "COMPARISON",     # Compare: "X vs Y"
        "HOWTO",          # Instructions: "How to X?"
        "RESEARCH",       # Open-ended: "Tell me about X"
        "PUZZLE",         # Multi-step: "Which X satisfies Y and Z?"
    ]
    
    async def classify(self, query: str, llm_config: dict) -> ClassificationResult:
        """One LLM call to classify query type + complexity + decomposition need."""
```

**Prompt template** (from LDR):
```
Classify this query:
Type: FACTUAL | TEMPORAL | PERSON | COMPARISON | HOWTO | RESEARCH | PUZZLE
Complexity: SIMPLE | MEDIUM | COMPLEX
Needs decomposition: YES | NO
If YES, suggest 2-5 subtasks.

Query: {query}

Output as JSON.
```

Integration: This REPLACES the Phase 1 `QueryIntel` intent detection for strategy routing. Phase 1's rule-based intent stays for search parameter tuning; the LLM classifier drives strategy selection.

### Task 2.2 — Adaptive Explorer (`strategy/adaptive_explorer.py`)
**Source**: `local-deep-research/candidate_exploration/adaptive_explorer.py`
**Effort**: 5 hours

```python
class AdaptiveExplorer:
    """
    Generates multiple query angles, tracks which work, and adapts.
    Used for RESEARCH and PUZZLE queries where a single search angle is insufficient.
    """
    
    STRATEGIES = ["direct", "synonym", "category", "related"]
    
    async def explore(self, query: str, searxng_client, llm_config) -> ExploreResult:
        """Generate multiple search angles, execute, track performance."""
        # For each strategy:
        #   direct: use query as-is
        #   synonym: LLM generates synonym-based query variant
        #   category: LLM generates broader category query
        #   related: LLM generates related-terms query
        # 
        # Execute all 4 via SearXNG (parallel)
        # Track: attempts, candidates_found, quality_score
        # Adapt: re-rank strategies based on performance
```

Key pattern from LDR:
- Each strategy gets `{attempts, candidates_found, quality_sum}` stats
- After N searches, re-rank strategies by `quality_sum / attempts`
- Adapt: prefer strategies with higher hit rates for this query type

### Task 2.3 — Recursive Decomposer (`strategy/recursive_decomposer.py`)
**Source**: `local-deep-research/strategies/recursive_decomposition_strategy.py`
**Effort**: 5 hours

```python
class RecursiveDecomposer:
    """
    For COMPLEX and PUZZLE queries: decompose into subtasks,
    recursively solve each, aggregate results.
    """
    
    MAX_DEPTH = 5
    
    async def decompose_and_solve(
        self, query: str, searxng_client, llm_config, depth: int = 0
    ) -> DecomposedResult:
        """LLM decides: can I answer directly? If not, split into subtasks."""
        
        # Step 1: LLM evaluates query
        #   "Can you answer this directly?" → YES/NO
        #   If YES → standard search + return
        #   If NO → generate subtasks with dependencies
        
        # Step 2: Generate subtasks
        #   LLM produces: SUBTASKS: [{id, query, dependencies}]
        #   Example: "What CRISPR therapies are approved vs in trials?"
        #     → Subtask 1: "List FDA-approved CRISPR therapies" (no deps)
        #     → Subtask 2: "List CRISPR therapies in clinical trials" (no deps)  
        #     → Subtask 3: "Compare approved vs trial therapies" (deps: [1,2])
        
        # Step 3: Solve subtasks (recursive, respecting dependencies)
        # Step 4: Aggregate with LLM
```

### Task 2.4 — Strategy Router Integration
**Effort**: 3 hours

Update `router.py` to dispatch through strategies:

```python
class BrowserGoat:
    async def search(self, query: str) -> SearchResult:
        # Phase 1 layers...
        
        # NEW: Phase 2 strategy dispatch
        classification = await self.query_classifier.classify(query, self.llm_config)
        
        if classification.type == "RESEARCH":
            results = await self.adaptive_explorer.explore(query, ...)
        elif classification.complexity == "COMPLEX" or classification.type == "PUZZLE":
            results = await self.recursive_decomposer.decompose_and_solve(query, ...)
        else:
            # Use Phase 1 default pipeline
            results = await self._default_search(query)
        
        # Layers 2-4 proceed as before...
```

### Task 2.5 — Tests
**Effort**: 4 hours

- Test classifier against 30+ known query types
- Test adaptive explorer strategy tracking and re-ranking
- Test decomposer with multi-step queries
- Integration: RESEARCH query uses adaptive explorer, PUZZLE query uses decomposer

---

## Phase 2 Completion Criteria

- [ ] Query classifier correctly routes 6+ query types
- [ ] Adaptive explorer generates 4 search angles, tracks performance, adapts
- [ ] Recursive decomposer breaks complex queries into solvable subtasks
- [ ] Strategy router dispatches correctly based on classification
- [ ] All tests pass, typecheck clean
- [ ] Phase 2 queries produce better results than Phase 1 for RESEARCH and COMPLEX types
