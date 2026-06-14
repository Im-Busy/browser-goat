"""Force Answer — synthesize a final answer when limits are hit.

Ported from Marco-DeepResearch prompts/inference.py: FORCE_ANSWER_PROMPT.
"""

from __future__ import annotations

from collections.abc import Sequence

FORCE_ANSWER_PROMPT = """You have reached the limit of your search. Based on the information gathered so far, provide your best possible answer.

## RULES
1. Synthesize only from the sources provided below.
2. Include inline citations like [1], [2] for every factual claim.
3. If the sources are truly insufficient to answer the query, state clearly what is known and what is missing.
4. Suggest specific next steps or alternative search angles.
5. Be honest about confidence level.

## SOURCES
{sources}

## QUERY
{query}

## YOUR ANSWER
"""


def build_force_answer_prompt(
    query: str,
    sources_text: str,
) -> str:
    """Build the force-answer prompt with query and source context.

    Args:
        query: The original search query.
        sources_text: Formatted source texts with [N] markers.

    Returns:
        Complete prompt string ready for LLM.
    """
    return FORCE_ANSWER_PROMPT.format(query=query, sources=sources_text)


def format_sources_for_prompt(
    sources: Sequence[object],
    max_source_chars: int = 3000,
) -> str:
    """Format a list of extracted sources for the force-answer prompt.

    Args:
        sources: List of source objects (must have url, evidence/summary attrs).
        max_source_chars: Max total characters for all sources combined.

    Returns:
        Formatted string with [N] markers per source.
    """
    if not sources:
        return "No sources available."

    formatted: list[str] = []
    total_chars = 0

    for i, source in enumerate(sources, 1):
        evidence = getattr(source, "evidence", "") or getattr(source, "summary", "") or getattr(source, "text", "")
        url = getattr(source, "url", "")

        entry = f"[{i}] {url}\n{evidence[:500]}"
        total_chars += len(entry)

        if total_chars > max_source_chars and formatted:
            formatted.append(f"... ({len(sources) - i + 1} more sources omitted)")
            break

        formatted.append(entry)

    return "\n\n".join(formatted)
