"""LLM-powered query classifier that routes queries to different strategies.

Ports classification patterns from local-deep-research:
  - smart_decomposition_strategy.py — LLM-based query type detection
  - adaptive_explorer.py — strategy routing by query shape

Provides both LLM-driven classification and a keyword-based fallback
inspired by the QueryIntel pattern from pre_search/query_intel.py.
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from typing import Any

from browsing_meta.models import ClassificationResult

# ── Query Type Labels ──────────────────────────────────────────────────────────

FACTUAL = "factual"
TEMPORAL = "temporal"
PERSON = "person"
COMPARISON = "comparison"
HOWTO = "howto"
RESEARCH = "research"
PUZZLE = "puzzle"

QUERY_TYPES = (FACTUAL, TEMPORAL, PERSON, COMPARISON, HOWTO, RESEARCH, PUZZLE)

# ── Prompt ────────────────────────────────────────────────────────────────────

CLASSIFIER_PROMPT = """You are a query classification system. Analyze the user's query and return a JSON object.

## Query
{query}

## Classification Rules

Classify into exactly one of these 7 types:
1. **factual** — Seeking a specific fact or definition ("What is the capital of France?", "What is photosynthesis?")
2. **temporal** — Time-sensitive, news, or recency-dependent ("What happened today?", "Latest stock market news")
3. **person** — About a specific person ("Who is Satya Nadella?", "Biography of Marie Curie")
4. **comparison** — Comparing two or more things ("Python vs Rust", "iPhone or Samsung?", "differences between A and B")
5. **howto** — Procedural, instructional, or troubleshooting ("How to deploy Docker?", "Steps to bake a cake")
6. **research** — Academic, deep-dive, or comprehensive ("Latest research on quantum computing", "Literature review of RLHF")
7. **puzzle** — Riddles, brain teasers, lateral thinking, logic puzzles, word games ("What has keys but can't open locks?", "Solve this riddle")

## Complexity
- **simple**: ≤8 words, single fact, straightforward
- **medium**: 9-15 words, some nuance, may need 2-3 sources
- **complex**: >15 words, multi-part, ambiguous, or requires synthesis

## Output Format
Return ONLY a valid JSON object with these fields:
- "query_type": one of the 7 types above
- "complexity": "simple", "medium", or "complex"
- "needs_decomposition": true if the query is complex and would benefit from being split into subtasks
- "suggested_subtasks": list of strings, empty list if no decomposition needed
- "confidence": float between 0.0 and 1.0 indicating classification confidence

IMPORTANT:
- Return ONLY valid JSON. No other text, no markdown formatting.
- If the query type is ambiguous, pick the best match and set confidence accordingly.
- For complex queries that combine multiple intents, set needs_decomposition=true and suggest subtasks.
"""

# ── Rule-Based Fallback Patterns ───────────────────────────────────────────────
# Borrowed and extended from QueryIntel pattern library

PERSON_PATTERNS: list[str] = [
    "who is ", "who was ", "who's ", "who are ",
    "biography of", "who founded", "who created",
    "who invented", "who discovered", "tell me about ",
    "profile of", "background of",
]

COMPARISON_PATTERNS: list[str] = [
    " vs ", " versus ", " or ",
    "difference between", "compare ", "comparison",
    "better than", "worse than", "pros and cons",
    "advantages and disadvantages", "differences between",
    "compared to", "similarities",
]

HOWTO_PATTERNS: list[str] = [
    "how to ", "how do i ", "how do you ",
    "how can i ", "how can you ", "how would i ",
    "tutorial", "guide to", "step by step",
    "steps to", "walkthrough", "instructions for",
    "way to ", "ways to ",
]

TEMPORAL_PATTERNS: list[str] = [
    "latest", "recent", "today", "now", "current",
    "breaking", "just in", "this week", "this month",
    "this year", "updated", "update", "news",
    "as of", "yesterday", "tomorrow",
]

RESEARCH_PATTERNS: list[str] = [
    "research", "study", "studies", "paper", "papers",
    "academic", "literature review", "meta-analysis",
    "systematic review", "state of the art", "survey of",
    "advances in", "developments in", "trends in",
    "comprehensive overview of", "deep dive into",
]

PUZZLE_PATTERNS: list[str] = [
    "puzzle", "riddle", "brain teaser", "lateral thinking",
    "what am i", "logic puzzle", "word puzzle",
    "crossword clue", "what has ", "who am i",
    "solve this", "can you solve",
]

DECOMPOSITION_SIGNALS: list[str] = [
    " and ", " or ", " also ", " additionally ",
    " furthermore ", " moreover ", "first", "second",
    "third", "finally", "lastly", "compare and contrast",
    "differences and similarities",
]

# ── Word Count Thresholds ──────────────────────────────────────────────────────

SIMPLE_MAX_WORDS = 8
COMPLEX_MIN_WORDS = 15

# ── Classifier ─────────────────────────────────────────────────────────────────


class QueryClassifier:
    """Classify search queries into types for strategy routing.

    Uses an LLM when available (via async callable), otherwise falls back
    to keyword-based classification matching the QueryIntel pattern.

    The LLM callable must have the signature:
        async def llm_call(messages: list[dict]) -> str
    """

    def __init__(self, llm_call: Callable[[list[dict[str, Any]]], Awaitable[str]] | None = None) -> None:
        """Initialize with optional LLM callable.

        Args:
            llm_call: Optional async function that takes a message list
                      and returns a string response.
        """
        self._llm_call = llm_call

    async def classify(
        self,
        query: str,
        llm_call: Callable[[list[dict[str, Any]]], Awaitable[str]] | None = None,
    ) -> ClassificationResult:
        """Classify a query into a type with complexity and decomposition metadata.

        Args:
            query: The user's search query.
            llm_call: Optional override LLM callable. If None, uses the
                      instance-level callable. If both are None, uses
                      rule-based fallback.

        Returns:
            ClassificationResult with query_type, complexity,
            needs_decomposition, suggested_subtasks, and confidence.
        """
        effective_llm = llm_call or self._llm_call

        if effective_llm is not None:
            return await self._classify_with_llm(query, effective_llm)

        return self._classify_rule_based(query)

    async def _classify_with_llm(
        self,
        query: str,
        llm_call: Callable[[list[dict[str, Any]]], Awaitable[str]],
    ) -> ClassificationResult:
        """Classify query using LLM with a structured prompt."""
        prompt = CLASSIFIER_PROMPT.format(query=query)
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]

        try:
            raw = await llm_call(messages)
            parsed = self._parse_llm_response(raw)
            return ClassificationResult(
                query_type=parsed.get("query_type", FACTUAL),
                complexity=parsed.get("complexity", "simple"),
                needs_decomposition=parsed.get("needs_decomposition", False),
                suggested_subtasks=parsed.get("suggested_subtasks", []),
                confidence=float(parsed.get("confidence", 0.5)),
            )
        except Exception:
            # Fallback to rule-based on any LLM failure
            return self._classify_rule_based(query)

    def _parse_llm_response(self, text: str) -> dict[str, Any]:
        """Parse JSON from LLM response, handling common formatting issues."""
        # Try direct JSON parse
        text = text.strip()
        try:
            return dict(json.loads(text))
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code blocks
        for pattern in [
            r"```(?:json)?\s*(\{.*?\})\s*```",
            r"\{[^}]*?query_type[^}]*?\}",
        ]:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    return dict(json.loads(match.group(1)))
                except (json.JSONDecodeError, IndexError):
                    continue

        # Last resort: try to find any JSON object
        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start != -1 and brace_end > brace_start:
            try:
                return dict(json.loads(text[brace_start : brace_end + 1]))
            except json.JSONDecodeError:
                pass

        return {}

    def _classify_rule_based(self, query: str) -> ClassificationResult:
        """Classify query using keyword pattern matching.

        Priority order (first match wins):
        PERSON → COMPARISON → HOWTO → TEMPORAL → RESEARCH → PUZZLE → FACTUAL
        """
        query_lower = query.lower().strip()
        word_count = len(query.split())

        # Determine complexity from word count
        complexity = self._rule_complexity(word_count, query_lower)

        # Detect type by pattern priority
        query_type = self._detect_type(query_lower)

        # Determine decomposition needs
        needs_decomp, subtasks = self._rule_decomposition(query_type, complexity, query_lower, word_count)

        # Confidence based on pattern match strength
        confidence = self._rule_confidence(query_type, query_lower)

        return ClassificationResult(
            query_type=query_type,
            complexity=complexity,
            needs_decomposition=needs_decomp,
            suggested_subtasks=subtasks,
            confidence=confidence,
        )

    def _detect_type(self, query_lower: str) -> str:
        """Detect query type via keyword matching with priority ordering."""
        # Person check
        for pattern in PERSON_PATTERNS:
            if pattern in query_lower:
                return PERSON

        # Comparison check
        for pattern in COMPARISON_PATTERNS:
            if pattern in query_lower:
                return COMPARISON
        if query_lower.startswith("difference between"):
            return COMPARISON

        # HowTo check
        for pattern in HOWTO_PATTERNS:
            if pattern in query_lower:
                return HOWTO

        # Temporal check (strong signals first)
        strong_temporal = {"today", "just in", "breaking", "this week", "this month", "yesterday"}
        if any(kw in query_lower for kw in strong_temporal):
            return TEMPORAL

        # Research check
        for pattern in RESEARCH_PATTERNS:
            if pattern in query_lower:
                return RESEARCH

        # Puzzle check
        for pattern in PUZZLE_PATTERNS:
            if pattern in query_lower:
                return PUZZLE

        # Soft temporal check
        for pattern in TEMPORAL_PATTERNS:
            if pattern in query_lower:
                return TEMPORAL

        # Default
        return FACTUAL

    def _rule_complexity(self, word_count: int, query_lower: str) -> str:
        """Determine complexity from word count and decomposition signals."""
        has_decomp = any(signal in query_lower for signal in DECOMPOSITION_SIGNALS)

        if word_count <= SIMPLE_MAX_WORDS and not has_decomp:
            return "simple"
        if word_count <= COMPLEX_MIN_WORDS and not has_decomp:
            return "medium"
        return "complex"

    def _rule_decomposition(
        self,
        query_type: str,
        complexity: str,
        query_lower: str,
        word_count: int,
    ) -> tuple[bool, list[str]]:
        """Determine if query needs decomposition and suggest subtasks."""
        if complexity != "complex":
            return False, []

        needs_decomp = True
        subtasks: list[str] = []

        if query_type == COMPARISON:
            # Try to split on vs/versus/or
            parts = re.split(r"\s+(?:vs\.?|versus|or)\s+", query_lower, maxsplit=1)
            if len(parts) >= 2:
                subtasks.append(f"Research: {parts[0].strip()}")
                subtasks.append(f"Research: {parts[1].strip()}")
                subtasks.append("Synthesize comparison")
            else:
                subtasks.append("Research each option")
                subtasks.append("Compare findings")
        elif query_type == HOWTO and word_count > COMPLEX_MIN_WORDS:
            subtasks.append("Identify prerequisites")
            subtasks.append("Find step-by-step instructions")
            subtasks.append("Verify instructions with multiple sources")
        elif query_type == RESEARCH:
            subtasks.append("Find recent papers and studies")
            subtasks.append("Summarize key findings")
            subtasks.append("Synthesize comprehensive answer")
        elif query_type == TEMPORAL:
            subtasks.append("Find latest developments")
            subtasks.append("Verify with multiple news sources")
            subtasks.append("Summarize current state")
        else:
            subtasks.append("Break down the question into key parts")
            subtasks.append("Research each part independently")
            subtasks.append("Combine findings into comprehensive answer")

        return needs_decomp, subtasks

    def _rule_confidence(self, query_type: str, query_lower: str) -> float:
        """Assign confidence score based on pattern match strength.

        Higher confidence when explicit patterns are matched, lower for
        default fallback (factual).
        """
        if query_type == FACTUAL:
            return 0.4  # Lowest confidence — it's the default

        # Explicit pattern matches get higher confidence based on match clarity
        pattern_count = sum(
            1 for p in self._patterns_for_type(query_type) if p in query_lower
        )
        if pattern_count >= 2:
            return 0.85
        if pattern_count == 1:
            return 0.7
        return 0.55

    def _patterns_for_type(self, query_type: str) -> list[str]:
        """Get the pattern list for a given query type."""
        mapping: dict[str, list[str]] = {
            PERSON: PERSON_PATTERNS,
            COMPARISON: COMPARISON_PATTERNS,
            HOWTO: HOWTO_PATTERNS,
            TEMPORAL: TEMPORAL_PATTERNS,
            RESEARCH: RESEARCH_PATTERNS,
            PUZZLE: PUZZLE_PATTERNS,
        }
        return mapping.get(query_type, [])
