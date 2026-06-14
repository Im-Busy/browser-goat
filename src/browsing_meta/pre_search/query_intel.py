"""Query Intelligence Engine — ported from SearchWala query_intel.rs.

Pure rule-based query analysis: intent classification, time sensitivity detection,
entity extraction, complexity scoring. Zero ML dependencies.
"""

from __future__ import annotations

from datetime import datetime

from browsing_meta.models import QueryAnalysis, QueryComplexity, QueryIntent

# ── Intent Classification ─────────────────────────────────────────────────────


NAV_SITES = [
    "github.com",
    "stackoverflow.com",
    "youtube.com",
    "reddit.com",
    "twitter.com",
    "x.com",
    "wikipedia.org",
    "amazon.com",
    "linkedin.com",
    "facebook.com",
    "instagram.com",
]

COMPARISON_PATTERNS = [
    " vs ",
    " versus ",
    " or ",
    " difference between",
    " compare ",
    " comparison",
    " better than",
    " worse than",
    " pros and cons",
    " advantages and disadvantages",
]

PERSON_PATTERNS = [
    "who is ",
    "who was ",
    "who's ",
    "biography of",
    "who founded",
    "who created",
    "who invented",
    "who discovered",
]

HOWTO_PATTERNS = [
    "how to ",
    "how do i ",
    "how do you ",
    "how can i ",
    "how can you ",
    "tutorial",
    "guide to",
    "step by step",
    "steps to",
]

TEMPORAL_PATTERNS = [
    "latest",
    "recent",
    "today",
    "now",
    "current",
    "breaking",
    "just in",
    "this week",
    "this month",
    "this year",
    "updated",
    "update",
    "news",
]

RESEARCH_PATTERNS = [
    "research",
    "study",
    "studies",
    "paper",
    "papers",
    "academic",
    "literature review",
    "meta-analysis",
    "systematic review",
    "state of the art",
    "survey of",
    "advances in",
    "developments in",
    "trends in",
]

# ── Entity Extraction ─────────────────────────────────────────────────────────

    # Common English stopwords + function words to avoid extracting as entities
# NOTE: Words commonly used in proper nouns (New, South, North, etc.) are
# NOT included here to avoid breaking entity extraction.
STOPWORDS: set[str] = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "up", "about", "into", "through", "during",
    "before", "after", "above", "below", "between", "out", "off", "over",
    "under", "again", "further", "then", "once", "here", "there", "when",
    "where", "why", "how", "all", "both", "each", "few", "more", "most",
    "other", "some", "such", "no", "nor", "not", "only", "own", "same",
    "so", "than", "too", "very", "can", "will", "just", "should", "now",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "having", "do", "does", "did", "doing", "would", "could",
    "may", "might", "must", "shall", "this", "that", "these", "those",
    "i", "me", "my", "myself", "we", "our", "ours", "ourselves", "you",
    "your", "yours", "yourself", "yourselves", "he", "him", "his",
    "himself", "she", "her", "hers", "herself", "it", "its", "itself",
    "they", "them", "their", "theirs", "themselves", "what", "which",
    "who", "whom", "whose",
    # Additional common words often in queries (NOT proper noun components)
    "best", "top", "old", "good", "bad", "better", "worse",
    "first", "last", "next", "previous", "high", "low", "big", "small",
    "many", "much", "little", "large", "great", "important", "different",
    "right", "left", "early", "late", "long", "short", "easy",
    "hard", "simple", "complex", "free", "open", "close", "real", "true",
    "false", "full", "empty", "main", "major", "minor", "possible",
    "available", "known", "unknown", "like", "also", "even", "still",
    "already", "always", "never", "often", "sometimes", "usually",
    "need", "want", "get", "make", "use", "using", "find", "found",
}


def _is_stopword(word: str) -> bool:
    """Check if a word is a stopword (case-insensitive)."""
    return word.lower() in STOPWORDS


def _is_capitalized(word: str) -> bool:
    """Check if a word starts with uppercase."""
    return len(word) > 0 and word[0].isupper()


# ── Query Intelligence Class ──────────────────────────────────────────────────


class QueryIntel:
    """Analyze search queries for intent, time sensitivity, entities, and complexity.

    Pure rule-based analysis with zero ML dependencies.
    Ported from SearchWala src/query_intel.rs.
    """

    def analyze(self, query: str) -> QueryAnalysis:
        """Full query analysis: intent + time + entities + complexity + source count.

        Args:
            query: Raw user query string.

        Returns:
            QueryAnalysis with all fields populated.
        """
        query_lower = query.lower().strip()

        intent = self._detect_intent(query_lower)
        is_time_sensitive = self._detect_temporal(query_lower)
        entities = self._extract_entities(query)
        complexity = self._score_complexity(query)
        optimal_sources = self._optimal_source_count(complexity, intent)
        news_boost = is_time_sensitive and intent in {QueryIntent.TEMPORAL, QueryIntent.RESEARCH}

        return QueryAnalysis(
            intent=intent,
            is_time_sensitive=is_time_sensitive,
            entities=entities,
            complexity=complexity,
            optimal_sources=optimal_sources,
            news_boost=news_boost,
        )

    def _detect_intent(self, query_lower: str) -> QueryIntent:
        """Classify query into one of 6 intent categories.

        Priority order (first match wins):
        NAVIGATIONAL → PERSON → COMPARISON → HOWTO → TEMPORAL → RESEARCH → FACTUAL
        """
        # Navigation check: queries pointing to specific sites
        is_nav = any(f"site:{site}" in query_lower or f" {site}" in query_lower
                     for site in NAV_SITES)
        if is_nav:
            return QueryIntent.RESEARCH  # Treated as research to gather info

        # Person check
        for pattern in PERSON_PATTERNS:
            if pattern in query_lower:
                return QueryIntent.PERSON

        # Comparison check — check both with and without leading space
        for pattern in COMPARISON_PATTERNS:
            if pattern in query_lower:
                return QueryIntent.COMPARISON
        # Also check for comparison patterns at start of query (no leading space)
        if query_lower.startswith("difference between"):
            return QueryIntent.COMPARISON

        # HowTo check
        for pattern in HOWTO_PATTERNS:
            if pattern in query_lower:
                return QueryIntent.HOWTO

        # Temporal check (explicitly temporal keywords)
        strong_temporal = {"today", "just in", "breaking", "this week", "this month"}
        if any(kw in query_lower for kw in strong_temporal):
            return QueryIntent.TEMPORAL

        # Research check
        for pattern in RESEARCH_PATTERNS:
            if pattern in query_lower:
                return QueryIntent.RESEARCH

        # Soft temporal check
        for pattern in TEMPORAL_PATTERNS:
            if pattern in query_lower:
                return QueryIntent.TEMPORAL

        # Default
        return QueryIntent.FACTUAL

    def _detect_temporal(self, query_lower: str) -> bool:
        """Detect if a query is time-sensitive.

        Three-tier check:
        1. Explicit recency keywords ("latest", "recent", "today", "news")
        2. Year references (2020-2030)
        3. Role queries that imply recency ("current CEO", etc.)
        """
        # Tier 1: Explicit recency keywords
        recency_keywords = [
            "latest", "recent", "today", "now", "current", "currently",
            "breaking", "just in", "this week", "this month", "this year",
            "updated", "news",
        ]
        if any(kw in query_lower for kw in recency_keywords):
            return True

        # Tier 2: Year references
        current_year = datetime.now().year
        for year in range(current_year - 5, current_year + 1):
            if str(year) in query_lower:
                return True

        # Tier 3: Role queries (implying recency)
        role_prefixes = [
            "current ceo of", "current president of", "current leader of",
            "current price of", "current value of", "current rate of",
            "current population of",
        ]
        return any(query_lower.startswith(prefix) for prefix in role_prefixes)

    def _extract_entities(self, query: str) -> list[str]:
        """Extract capitalized proper noun sequences from query.

        A sequence of capitalized words (not at sentence start) is treated
        as a named entity. Filtered through stopword list.
        """
        words = query.split()
        entities: list[str] = []
        i = 0

        while i < len(words):
            word = words[i].strip(",.;:!?\"'()[]{}")

            # Skip stopwords and non-capitalized words
            if _is_stopword(word) or not _is_capitalized(word):
                i += 1
                continue

            # Skip single capitalized words that are just stopwords
            if len(word) <= 1:
                i += 1
                continue

            # Build multi-word entity sequence
            entity_words = [word]
            j = i + 1
            while j < len(words):
                next_word = words[j].strip(",.;:!?\"'()[]{}")
                if _is_stopword(next_word):
                    break
                if _is_capitalized(next_word) and len(next_word) > 1:
                    entity_words.append(next_word)
                    j += 1
                else:
                    break

            entity = " ".join(entity_words)
            # Filter out common false positives
            if not self._is_false_positive(entity):
                entities.append(entity)

            i = j

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique = []
        for e in entities:
            if e.lower() not in seen:
                seen.add(e.lower())
                unique.append(e)
        return unique

    def _is_false_positive(self, entity: str) -> bool:
        """Filter out common false positive entity extractions."""
        false_positives = {
            "I", "I'm", "I'll", "I've", "I'd",
            "Can", "Will", "Should", "Would", "Could",
            "What", "When", "Where", "Why", "How", "Which", "Who",
        }
        return entity in false_positives

    def _score_complexity(self, query: str) -> QueryComplexity:
        """Score query complexity based on word count and structure.

        Simple: ≤5 words
        Medium: 6-12 words
        Complex: >12 words or contains decomposition signals
        """
        words = query.split()
        word_count = len(words)

        # Decomposition signals: multi-part questions
        decomp_signals = [" and ", " or ", " also ", " additionally ",
                          " furthermore ", " moreover ", "first", "second",
                          "third", "finally", "lastly"]
        has_decomp = any(signal in query.lower() for signal in decomp_signals)

        if word_count <= 5 and not has_decomp:
            return QueryComplexity.SIMPLE
        elif word_count <= 12 or (word_count <= 15 and not has_decomp):
            return QueryComplexity.MEDIUM
        else:
            return QueryComplexity.COMPLEX

    def _optimal_source_count(
        self, complexity: QueryComplexity, intent: QueryIntent
    ) -> int:
        """Determine optimal number of sources to retrieve.

        Lookup table based on complexity and intent.
        """
        table: dict[QueryComplexity, dict[QueryIntent, int]] = {
            QueryComplexity.SIMPLE: {
                QueryIntent.FACTUAL: 10,
                QueryIntent.PERSON: 10,
                QueryIntent.TEMPORAL: 12,
                QueryIntent.COMPARISON: 12,
                QueryIntent.HOWTO: 12,
                QueryIntent.RESEARCH: 15,
            },
            QueryComplexity.MEDIUM: {
                QueryIntent.FACTUAL: 15,
                QueryIntent.PERSON: 15,
                QueryIntent.TEMPORAL: 18,
                QueryIntent.COMPARISON: 18,
                QueryIntent.HOWTO: 18,
                QueryIntent.RESEARCH: 25,
            },
            QueryComplexity.COMPLEX: {
                QueryIntent.FACTUAL: 20,
                QueryIntent.PERSON: 20,
                QueryIntent.TEMPORAL: 25,
                QueryIntent.COMPARISON: 25,
                QueryIntent.HOWTO: 25,
                QueryIntent.RESEARCH: 35,
            },
        }
        return table.get(complexity, {}).get(intent, 15)

    def enrich_query(self, query: str, analysis: QueryAnalysis) -> str:
        """Enrich query with temporal context if time-sensitive.

        Appends current year to time-sensitive queries for recency.
        """
        if analysis.is_time_sensitive:
            current_year = str(datetime.now().year)
            if current_year not in query:
                return f"{query} {current_year}"
        return query
