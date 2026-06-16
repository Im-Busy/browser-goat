"""Recursive query decomposition for complex multi-part questions.

Ports recursive decomposition patterns from local-deep-research:
  - recursive_decomposition_strategy.py — LLM decides whether to decompose,
    generates subtasks with dependencies, recursively solves, aggregates.

The decomposer turns complex multi-part queries into a directed acyclic graph
of subtasks, solves them respecting dependencies (parallel where possible),
and merges results via LLM synthesis.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from typing import Any

from browser_goat.models import DecomposedResult, SubTask
from browser_goat.searxng_client import SearXNGClient

# ── Depth Limit ─────────────────────────────────────────────────────────────────

MAX_DEPTH = 5

# ── Prompts ─────────────────────────────────────────────────────────────────────

CAN_ANSWER_DIRECTLY_PROMPT = """You are a query decomposition analyzer. Determine whether the following question can be answered directly with a single web search, or whether it needs to be broken down into multiple sub-questions.

## Question
{query}

## Instructions
Respond with a JSON object containing:
- "can_answer_directly": true or false
- "reasoning": A brief explanation of your decision

Answer true ONLY if the question is:
- A single, straightforward fact/lookup question
- Can be addressed by searching once
- Does NOT require synthesizing multiple distinct pieces of information

Answer false if the question:
- Has multiple distinct parts that require different searches
- Requires comparing or contrasting multiple entities
- Requires gathering information from different domains or angles
- Is a multi-step research question

Return ONLY valid JSON. No other text."""

DECOMPOSE_PROMPT = """You are a query decomposition system. Break down the following complex question into a set of sub-questions (subtasks) that can be answered independently or with known dependencies.

## Original Question
{query}

## Instructions
Generate 2-5 subtasks that together answer the original question. Each subtask must:
1. Be self-contained and independently answerable via web search
2. Have a unique id (e.g., "sub_1", "sub_2")
3. List dependencies as a list of subtask IDs that must be completed first
4. Use dependencies ONLY when one subtask's answer is needed to formulate another

## Output Format
Return ONLY a valid JSON array of objects with these fields:
- "id": string (e.g., "sub_1")
- "query": string (the search query for this subtask)
- "dependencies": list of strings (empty list if no dependencies)

Example:
[
    {{
        "id": "sub_1",
        "query": "What are the key features of product X?",
        "dependencies": []
    }},
    {{
        "id": "sub_2",
        "query": "What is the price of product X?",
        "dependencies": ["sub_1"]
    }}
]

Return ONLY valid JSON. No other text."""

AGGREGATE_PROMPT = """You are a query synthesis system. Combine the results of multiple sub-questions into a comprehensive answer to the original question.

## Original Question
{query}

## Sub-Question Results
{subtask_results}

## Instructions
Synthesize a coherent, comprehensive answer that:
1. Directly addresses the original question
2. Integrates information from all subtask results
3. Resolves any contradictions between sources
4. Presents information in a logical, well-structured manner
5. Cites specific subtask IDs where relevant

## Output
Write your synthesized answer below:"""


class RecursiveDecomposer:
    """Recursive query decomposition for complex multi-part questions.

    Decides whether to decompose a query, generates subtasks with
    dependencies, recursively solves them (parallel where possible),
    and aggregates results via LLM synthesis.

    The LLM callable must have the signature:
        async def llm_call(messages: list[dict]) -> str
    """

    def __init__(self, max_depth: int = MAX_DEPTH) -> None:
        """Initialize with optional depth limit override.

        Args:
            max_depth: Maximum recursion depth (default: 5).
        """
        self.max_depth = max_depth

    async def decompose_and_solve(
        self,
        query: str,
        searxng_client: SearXNGClient,
        llm_call: Callable[[list[dict[str, Any]]], Awaitable[str]],
        depth: int = 0,
    ) -> DecomposedResult:
        """Recursively decompose and solve a query.

        Args:
            query: The user's search query.
            searxng_client: Async SearXNG client for web search.
            llm_call: Async function that takes a message list and returns
                      a string response. Must handle both classification
                      prompts and answer synthesis.
            depth: Current recursion depth (0-indexed).

        Returns:
            DecomposedResult with subtasks, aggregated_answer, and depth info.

        Raises:
            ValueError: If llm_call is None and decomposition is needed.
        """
        if llm_call is None:
            raise ValueError("llm_call required for decomposition")

        # ── Step 1: Ask LLM if query can be answered directly ──────────────
        can_direct, _ = await self._check_can_answer_directly(query, llm_call)

        # Force direct answer if we're near the max depth
        if depth >= self.max_depth - 1:
            can_direct = True

        if can_direct:
            return await self._solve_direct(query, searxng_client, llm_call, depth)

        # ── Step 2: Generate subtasks ──────────────────────────────────────
        subtask_defs = await self._generate_subtasks(query, llm_call)
        subtasks = [
            SubTask(
                id=s["id"],
                query=s["query"],
                dependencies=s.get("dependencies", []),
            )
            for s in subtask_defs
        ]

        if not subtasks:
            # LLM produced no subtasks — fall back to direct solve
            return await self._solve_direct(query, searxng_client, llm_call, depth)

        # ── Step 3: Dependency-aware execution ────────────────────────────
        completed: dict[str, SubTask] = {}
        pending: set[str] = {st.id for st in subtasks}

        while pending:
            # Find tasks whose dependencies are all satisfied
            ready = [
                st
                for st in subtasks
                if st.id in pending
                and all(dep in completed for dep in st.dependencies)
            ]

            if not ready:
                # Circular or otherwise unsatisfiable deps — force-execute
                # all remaining pending tasks (they'll get partial answers)
                ready = [st for st in subtasks if st.id in pending]
                if not ready:
                    break

            # Execute ready tasks in parallel via recursive decomposition
            branch_results = await asyncio.gather(*[
                self.decompose_and_solve(
                    st.query, searxng_client, llm_call, depth + 1
                )
                for st in ready
            ])

            for st, branch in zip(ready, branch_results, strict=True):
                st.status = "completed"
                st.result = branch.aggregated_answer
                completed[st.id] = st
                pending.discard(st.id)

        # ── Step 4: Aggregate results ──────────────────────────────────────
        subtask_text = "\n\n".join(
            f"## {st.id}: {st.query}\n{st.result or '(no result)'}"
            for st in subtasks
        )
        aggregated = await self._aggregate_results(query, subtask_text, llm_call)

        return DecomposedResult(
            subtasks=subtasks,
            depth=depth,
            aggregated_answer=aggregated,
            intermediate_results=list(completed.values()),
        )

    async def _check_can_answer_directly(
        self,
        query: str,
        llm_call: Callable[[list[dict[str, Any]]], Awaitable[str]],
    ) -> tuple[bool, str]:
        """Ask LLM whether the query can be answered directly.

        Returns:
            Tuple of (can_answer_directly, reasoning).
        """
        prompt = CAN_ANSWER_DIRECTLY_PROMPT.format(query=query)
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]

        try:
            raw = await llm_call(messages)
            parsed = self._parse_json_response(raw)
            can_direct = bool(parsed.get("can_answer_directly", False))
            reasoning = str(parsed.get("reasoning", ""))
            return can_direct, reasoning
        except Exception:
            # Default to direct answer on any parse or call failure
            return True, ""

    async def _generate_subtasks(
        self,
        query: str,
        llm_call: Callable[[list[dict[str, Any]]], Awaitable[str]],
) -> list[dict[str, Any]]:
        """Ask LLM to decompose the query into subtasks with dependencies.

        Returns:
            List of dicts with keys: id, query, dependencies.
            Empty list if generation fails.
        """
        prompt = DECOMPOSE_PROMPT.format(query=query)
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]

        try:
            raw = await llm_call(messages)
            parsed = self._parse_json_response(raw)
            if isinstance(parsed, list):
                return [dict(item) for item in parsed]
            if isinstance(parsed, dict):
                # Some LLMs wrap the array in a top-level key
                for key in ("subtasks", "tasks", "items"):
                    if key in parsed and isinstance(parsed[key], list):
                        return [dict(item) for item in parsed[key]]
                return []
            return []
        except Exception:
            return []

    async def _solve_direct(
        self,
        query: str,
        searxng_client: SearXNGClient,
        llm_call: Callable[[list[dict[str, Any]]], Awaitable[str]],
        depth: int,
    ) -> DecomposedResult:
        """Solve a query directly with a single search + LLM answer.

        This is the leaf-node resolution path: search the web, then
        have the LLM synthesize an answer from the results.
        """
        search_results = await searxng_client.search(query)
        snippets = "\n".join(
            f"- [{r.title}]({r.url}): {r.content}"
            for r in search_results[:10]
        )
        answer = await self._answer_with_context(query, snippets, llm_call)
        return DecomposedResult(
            subtasks=[],
            depth=depth,
            aggregated_answer=answer,
            intermediate_results=[],
        )

    async def _answer_with_context(
        self,
        query: str,
        snippets: str,
        llm_call: Callable[[list[dict[str, Any]]], Awaitable[str]],
    ) -> str:
        """Generate a direct answer from search result snippets."""
        prompt = f"""You are a search answer system. Answer the following question based on the provided search results.

## Question
{query}

## Search Results
{snippets}

## Instructions
Provide a concise, accurate answer based on the search results above.
If the search results don't contain enough information, say so.
Cite specific sources where relevant.

## Answer"""
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]

        try:
            return str(await llm_call(messages))
        except Exception:
            return f"Unable to answer: {query}"

    async def _aggregate_results(
        self,
        query: str,
        subtask_results: str,
        llm_call: Callable[[list[dict[str, Any]]], Awaitable[str]],
    ) -> str:
        """Merge subtask results into a comprehensive synthesized answer."""
        prompt = AGGREGATE_PROMPT.format(
            query=query,
            subtask_results=subtask_results,
        )
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]

        try:
            return str(await llm_call(messages))
        except Exception:
            # Fallback: concatenate subtask results as-is
            return subtask_results

    def _parse_json_response(self, text: str) -> Any:
        """Parse JSON from LLM response, handling common formatting issues."""
        text = text.strip()

        # Try direct JSON parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code blocks (array or object)
        for pattern in [
            r"```(?:json)?\s*(\[.*?\])\s*```",
            r"```(?:json)?\s*(\{.*?\})\s*```",
        ]:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except (json.JSONDecodeError, IndexError):
                    continue

        # Last resort: find first JSON-like structure in the text
        for start_char, end_char in [("{", "}"), ("[", "]")]:
            start = text.find(start_char)
            end = text.rfind(end_char)
            if start != -1 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    continue

        return {}
