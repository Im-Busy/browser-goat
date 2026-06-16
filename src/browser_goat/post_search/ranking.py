"""Hybrid Ranking Engine — RRF + BM25+ + MMR.

Ported from SearchWala src/ranking.rs (v6.1.0).
Three-stage pipeline:
  Stage A: RRF (Reciprocal Rank Fusion) — cross-engine consensus
  Stage B: BM25+ — paragraph-level relevance scoring
  Stage D: MMR (Maximal Marginal Relevance) — diversity reranking
"""

from __future__ import annotations

import math
import re
from collections import Counter

from browser_goat.models import CleanedResult, RankedResult

# ── Constants (from SearchWala ranking.rs) ────────────────────────────────────

RRF_K = 60  # Cormack 2009 constant
BM25_K1 = 1.2  # term frequency saturation
BM25_B = 0.75  # length normalization
BM25_DELTA = 1.0  # Lv & Zhai 2011 lower bound (guarantees positive scores)
MMR_LAMBDA = 0.7  # relevance vs diversity tradeoff
CHUNK_MIN = 40  # minimum chunk size in characters
CHUNK_MAX = 600  # maximum chunk size in characters
CHUNK_OVERLAP = 0.15  # 15% overlap between chunks
MAX_CHUNKS_PER_URL = 3  # max chunks per URL in top-k MMR results

# 150 stopwords (SMART + extensions) from SearchWala ranking.rs
STOPWORDS: set[str] = {
    "a", "an", "the", "and", "or", "but", "if", "because", "as", "until",
    "while", "of", "at", "by", "for", "with", "about", "against", "between",
    "into", "through", "during", "before", "after", "above", "below", "to",
    "from", "up", "down", "in", "out", "on", "off", "over", "under", "again",
    "further", "then", "once", "here", "there", "when", "where", "why", "how",
    "all", "both", "each", "few", "more", "most", "other", "some", "such",
    "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very",
    "can", "will", "just", "should", "now",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "having", "do", "does", "did", "doing", "would", "could", "may", "might",
    "must", "shall", "this", "that", "these", "those", "i", "me", "my", "we",
    "our", "you", "your", "he", "him", "his", "she", "her", "it", "its", "they",
    "them", "their", "what", "which", "who", "whom", "am", "also", "even", "still", "already", "always", "never", "often", "sometimes",
    "usually", "well", "back",
}

# ── Engine Reliability Weights ─────────────────────────────────────────────────

# Tier 1: Primary search engines (1.5x weight)
ENGINE_WEIGHTS: dict[str, float] = {
    "google": 1.5,
    "bing": 1.2,
    "duckduckgo": 1.0,
    "brave": 1.0,
    "yahoo": 1.0,
    "wikipedia": 1.2,
    "scholar": 1.3,
    "arxiv": 1.3,
}


class HybridRanker:
    """Three-stage hybrid ranking pipeline.

    Stage A: RRF — cross-engine consensus (which results appear across engines?)
    Stage B: BM25+ — paragraph-level relevance to the query
    Stage D: MMR — diversity reranking to avoid redundant sources
    """

    def rank(
        self,
        results: list[CleanedResult],
        query: str,
        max_results: int = 15,
    ) -> list[RankedResult]:
        """Execute the full ranking pipeline.

        Args:
            results: Cleaned and deduplicated search results.
            query: The original search query.
            max_results: Maximum number of results to return.

        Returns:
            Ranked results sorted by final_score descending.
        """
        if not results:
            return []

        # Stage A: RRF scoring
        rrf_scored = self._compute_rrf(results)

        # Stage B: BM25+ paragraph-level relevance
        bm25_scored = self._compute_bm25(rrf_scored, query)

        # Stage D: MMR diversity reranking
        mmr_scored = self._compute_mmr(bm25_scored, query)

        # Sort by final score
        mmr_scored.sort(key=lambda r: r.final_score, reverse=True)

        # Assign ranks
        for i, result in enumerate(mmr_scored[:max_results]):
            result.rank = i + 1

        return mmr_scored[:max_results]

    # ── Stage A: Reciprocal Rank Fusion ──────────────────────────────────────

    def _compute_rrf(self, results: list[CleanedResult]) -> list[RankedResult]:
        """Compute RRF scores based on cross-engine consensus.

        Each result gets a score based on its position in each engine's results:
            score = Σ engine_weight / (RRF_K + position)
        """
        # Group results by engine
        engine_results: dict[str, list[CleanedResult]] = {}
        for r in results:
            if r.is_duplicate or r.blocked_reason:
                continue
            engine = r.engine or "unknown"
            engine_results.setdefault(engine, []).append(r)

        # Compute RRF for each result
        ranked: list[RankedResult] = []
        for r in results:
            weight = ENGINE_WEIGHTS.get(r.engine, 1.0)

            # Find this result's position in its engine's results
            engine_list = engine_results.get(r.engine, [])
            try:
                position = engine_list.index(r) + 1  # 1-indexed
            except ValueError:
                position = len(engine_list) + 1

            rrf_score = weight / (RRF_K + position)

            ranked.append(
                RankedResult(
                    **r.model_dump(),
                    rrf_score=rrf_score,
                )
            )

        return ranked

    # ── Stage B: BM25+ ───────────────────────────────────────────────────────

    def _compute_bm25(
        self, results: list[RankedResult], query: str
    ) -> list[RankedResult]:
        """Compute BM25+ paragraph-level relevance scores.

        For each result, chunk the content into paragraphs, tokenize,
        and score each chunk against the query using BM25+ (with delta).
        """
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return results

        # Collect all chunks for corpus statistics
        all_chunks: list[tuple[int, str]] = []  # (result_index, chunk_text)
        for i, result in enumerate(results):
            if result.content:
                chunks = self._chunk_text(result.content)
                for chunk in chunks:
                    all_chunks.append((i, chunk))

        if not all_chunks:
            return results

        # Corpus statistics
        corpus_tokens = [self._tokenize(chunk) for _, chunk in all_chunks]
        avg_doc_length = sum(len(t) for t in corpus_tokens) / len(corpus_tokens) if corpus_tokens else 0
        total_docs = len(corpus_tokens)

        # IDF calculation
        df: Counter[str] = Counter()
        for tokens in corpus_tokens:
            df.update(set(tokens))
        idf: dict[str, float] = {}
        for term, count in df.items():
            idf[term] = math.log((total_docs - count + 0.5) / (count + 0.5) + 1.0)

        # Score each result by its best chunks
        for i, result in enumerate(results):
            chunks_for_result = [c for idx, c in all_chunks if idx == i]
            if not chunks_for_result:
                result.final_score = result.rrf_score
                continue

            chunk_scores: list[float] = []
            for chunk in chunks_for_result:
                tokens = self._tokenize(chunk)
                if not tokens:
                    continue

                doc_length = len(tokens)
                tf: Counter[str] = Counter(tokens)

                score = 0.0
                for term in query_tokens:
                    if term not in idf:
                        continue
                    term_tf = tf.get(term, 0)
                    if term_tf == 0:
                        continue

                    # BM25+ formula: BM25(t,d) + delta * IDF(t)
                    numerator = term_tf * (BM25_K1 + 1)
                    denominator = term_tf + BM25_K1 * (
                        1 - BM25_B + BM25_B * doc_length / max(avg_doc_length, 1)
                    )
                    bm25 = idf[term] * numerator / denominator
                    score += bm25 + BM25_DELTA * idf[term]

                # Exact phrase bonus
                if query.lower() in chunk.lower():
                    score *= 1.25

                # Title match bonus
                if result.title:
                    title_tokens = set(self._tokenize(result.title.lower()))
                    query_token_set = set(query_tokens)
                    title_matches = len(title_tokens & query_token_set)
                    score += title_matches * 0.5

                chunk_scores.append(score)

            # Normalize RRF boost (multiply BM25 by 1.0-1.5 based on RRF)
            rrf_boost = 1.0 + min(result.rrf_score * 5, 0.5)

            # Best chunk score
            best_bm25 = max(chunk_scores) if chunk_scores else 0.0
            result.bm25_score = best_bm25
            result.final_score = best_bm25 * rrf_boost

        return results

    # ── Stage D: Maximal Marginal Relevance ──────────────────────────────────

    def _compute_mmr(
        self, results: list[RankedResult], query: str
    ) -> list[RankedResult]:
        """Apply MMR diversity reranking.

        Balances relevance (final_score) with novelty (dissimilarity to
        already-selected results) using Jaccard token-set similarity.
        """
        if len(results) <= 1:
            return results

        query_tokens = set(self._tokenize(query))
        selected: list[RankedResult] = []
        remaining = list(results)

        # First: pick the highest-scoring result
        remaining.sort(key=lambda r: r.final_score, reverse=True)
        best = remaining.pop(0)
        best.mmr_score = best.final_score
        selected.append(best)

        url_chunk_count: dict[str, int] = {best.url: 1}

        while remaining and len(selected) < len(results):
            best_idx = -1
            best_mmr = float("-inf")

            for idx, candidate in enumerate(remaining):
                # Relevance term
                relevance = MMR_LAMBDA * candidate.final_score

                # Diversity term: max Jaccard similarity to any selected
                max_sim = 0.0
                if query_tokens:
                    candidate_tokens = set(self._tokenize(candidate.content))
                    for sel in selected:
                        sel_tokens = set(self._tokenize(sel.content))
                        if sel_tokens and candidate_tokens:
                            intersection = len(candidate_tokens & sel_tokens)
                            union = len(candidate_tokens | sel_tokens)
                            sim = intersection / union if union > 0 else 0.0
                            max_sim = max(max_sim, sim)

                mmr = relevance - (1 - MMR_LAMBDA) * max_sim

                # Cap chunks per URL
                url_count = url_chunk_count.get(candidate.url, 0)
                if url_count >= MAX_CHUNKS_PER_URL:
                    mmr = float("-inf")

                if mmr > best_mmr:
                    best_mmr = mmr
                    best_idx = idx

            if best_idx < 0:
                break

            chosen = remaining.pop(best_idx)
            chosen.mmr_score = best_mmr
            chosen.final_score = best_mmr
            url_chunk_count[chosen.url] = url_chunk_count.get(chosen.url, 0) + 1
            selected.append(chosen)

        return selected

    # ── Text Processing Utilities ────────────────────────────────────────────

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text: split non-alphanumeric, lowercase, filter stopwords.

        Min token length: 2 characters.
        """
        if not text:
            return []

        tokens = re.split(r"[^a-zA-Z0-9]+", text.lower())
        return [
            t for t in tokens
            if len(t) >= 2 and t not in STOPWORDS
        ]

    def _chunk_text(self, text: str) -> list[str]:
        """Split text into overlapping paragraph chunks.

        Sentence-boundary-aware chunking with 15% overlap.
        Chunk size: 80-600 characters.
        """
        if not text:
            return []

        # Normalize whitespace
        text = re.sub(r"\s+", " ", text).strip()

        # Split at paragraph boundaries first
        paragraphs = re.split(r"\n\s*\n", text)

        chunks: list[str] = []
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # If paragraph fits in one chunk, use it directly
            if len(para) <= CHUNK_MAX:
                if len(para) >= CHUNK_MIN:
                    chunks.append(para)
                continue

            # Split long paragraphs at sentence boundaries
            sentences = self._split_sentences(para)
            current_chunk = ""

            for sentence in sentences:
                if len(current_chunk) + len(sentence) <= CHUNK_MAX:
                    current_chunk = (current_chunk + " " + sentence).strip()
                else:
                    if len(current_chunk) >= CHUNK_MIN:
                        chunks.append(current_chunk)
                    current_chunk = sentence

            if len(current_chunk) >= CHUNK_MIN:
                chunks.append(current_chunk)

        # Apply 15% overlap between consecutive chunks
        overlapped = self._apply_overlap(chunks)
        return overlapped

    def _split_sentences(self, text: str) -> list[str]:
        """Split text at sentence boundaries (. ! ? followed by space + capital)."""
        # Split on sentence-ending punctuation followed by space
        parts = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
        return [p.strip() for p in parts if p.strip()]

    def _apply_overlap(self, chunks: list[str]) -> list[str]:
        """Apply 15% character overlap between consecutive chunks."""
        if len(chunks) <= 1:
            return chunks

        result = [chunks[0]]
        for i in range(1, len(chunks)):
            prev = chunks[i - 1]
            current = chunks[i]

            # Take suffix of previous chunk as prefix for current
            overlap_chars = int(len(prev) * CHUNK_OVERLAP)
            if overlap_chars > 0:
                # Find a sentence boundary in the overlap region
                suffix = prev[-overlap_chars:]
                # Prepend to current
                current = suffix + " " + current

            result.append(current)

        return result
