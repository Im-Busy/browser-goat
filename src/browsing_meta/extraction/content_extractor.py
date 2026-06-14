"""7-Tier Cascading Content Extractor — ported from SearchWala extractor.rs.

Tries 7 strategies in priority order, falling through on failure:
  Tier 1: JSON-LD structured data (schema.org/Article, NewsArticle, BlogPosting)
  Tier 2: Structured CSS selectors (35+ CMS-specific patterns)
  Tier 3: Semantic HTML5 elements (article, main, [role="main"])
  Tier 4: Scored container (text density - link penalty)
  Tier 5: Content element aggregation (p, h1-h6, li, blockquote)
  Tier 6: Meta/og:description fallback
  Tier 7: Full body text (last resort)
"""

from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup, Tag

from browsing_meta.models import ExtractedContent

# ── CSS Selector Patterns ─────────────────────────────────────────────────────

# 35+ CMS-specific content selectors (from SearchWala extractor.rs)
CONTENT_SELECTORS: list[str] = [
    # WordPress
    ".entry-content", ".post-content", ".article-content",
    ".the-content", ".content-area article",
    # Medium
    "article .section-content",
    # Ghost
    ".post-content", ".gh-content",
    # Generic blog
    ".article-body", ".article__body", ".post-body",
    # News sites
    ".story-body", ".article-text", ".article-body__content",
    # Documentation
    ".markdown-body", ".doc-content", ".documentation-content",
    # Common patterns
    '[itemprop="articleBody"]', '[property="articleBody"]',
    "#article-body", "#content-body", "#main-content",
    ".content article", "main article",
    ".prose", ".rich-text", ".wysiwyg",
    # Additional CMS
    ".blog-content", ".single-content", ".page-content",
    ".entry", "#content", ".main-content",
]

# HTML5 semantic elements for content extraction
SEMANTIC_SELECTORS: list[str] = [
    "article", "main", '[role="main"]',
    ".post", ".article",
]

# Content-bearing elements for aggregation
CONTENT_ELEMENTS: list[str] = [
    "p", "h1", "h2", "h3", "h4", "h5", "h6",
    "li", "blockquote", "pre", "code",
    "td", "th", "dd", "dt",
]

# Boilerplate regex patterns to filter out
BOILERPLATE_PATTERNS: list[str] = [
    r"(?i)cookie (consent|policy|notice)",
    r"(?i)subscribe to (our )?(newsletter|updates)",
    r"(?i)click here to (read more|continue|accept)",
    r"(?i)(sign|log) (in|up|out)",
    r"(?i)advertisement|sponsored content",
    r"(?i)share (this|on|with)",
    r"(?i)follow (us|me) on",
    r"(?i)all rights reserved",
    r"(?i)copyright \d{4}",
    r"(?i)terms (of|and) (service|use|conditions)",
    r"(?i)privacy (policy|notice|statement)",
    r"(?i)we use cookies",
    r"(?i)please (enable|disable)",
    r"(?i)your browser does not support",
    r"(?i)(navigation|sidebar|footer|header|menu|breadcrumb)",
]


class ContentExtractor:
    """Extract clean article text from HTML using 7-tier cascading strategy.

    Each tier is tried in order. If a tier produces usable text (≥50 chars),
    it wins. Otherwise, fall through to the next tier.
    """

    def __init__(self, min_text_length: int = 50) -> None:
        self.min_text_length = min_text_length

    def extract(self, html: str, url: str) -> ExtractedContent:
        """Extract title and clean text from HTML.

        Args:
            html: Raw HTML content.
            url: Source URL (for logging/metadata).

        Returns:
            ExtractedContent with title, text, and tier info.
        """
        if not html or not html.strip():
            return ExtractedContent(
                url=url,
                extraction_tier=0,
            )

        soup = BeautifulSoup(html, "lxml")

        # Extract title once (used by all tiers)
        title = self._extract_title(soup)

        # Tier 1: JSON-LD structured data
        result = self._try_json_ld(soup, url, title)
        if result:
            return result

        # Tier 2: Structured CSS selectors
        result = self._try_css_selectors(soup, url, title)
        if result:
            return result

        # Tier 3: Semantic HTML5
        result = self._try_semantic(soup, url, title)
        if result:
            return result

        # Tier 4: Scored container
        result = self._try_scored(soup, url, title)
        if result:
            return result

        # Tier 5: Content element aggregation
        result = self._try_elements(soup, url, title)
        if result:
            return result

        # Tier 6: Meta description fallback
        result = self._try_meta(soup, url, title)
        if result:
            return result

        # Tier 7: Full body (last resort)
        body = soup.find("body")
        text = body.get_text(separator=" ", strip=True) if body else ""
        text = self._clean_text(text)

        return ExtractedContent(
            url=url,
            title=title,
            text=text,
            extraction_tier=7,
            word_count=len(text.split()) if text else 0,
        )

    # ── Tier 1: JSON-LD ──────────────────────────────────────────────────────

    def _try_json_ld(
        self, soup: BeautifulSoup, url: str, title: str
    ) -> ExtractedContent | None:
        """Try extracting from JSON-LD structured data."""
        scripts = soup.find_all("script", type="application/ld+json")
        for script in scripts:
            try:
                data = json.loads(script.string or "")
            except (json.JSONDecodeError, TypeError):
                continue

            # Handle @graph (multiple entities)
            items: list[dict[str, Any]] = []
            if isinstance(data, dict):
                items = data.get("@graph", [data])

            for item in items:
                article_body = item.get("articleBody") or item.get("description") or ""
                if article_body and len(article_body.strip()) >= self.min_text_length:
                    return ExtractedContent(
                        url=url,
                        title=item.get("headline") or title,
                        text=self._clean_text(str(article_body)),
                        extraction_tier=1,
                        word_count=len(article_body.split()),
                        metadata={"schema_type": item.get("@type", "")},
                    )

        return None

    # ── Tier 2: CSS Selectors ────────────────────────────────────────────────

    def _try_css_selectors(
        self, soup: BeautifulSoup, url: str, title: str
    ) -> ExtractedContent | None:
        """Try extraction using known CSS selectors for content areas."""
        for selector in CONTENT_SELECTORS:
            try:
                elements = soup.select(selector)
            except Exception:
                continue

            for element in elements:
                # Remove nav, aside, footer within content area
                for tag in element.find_all(["nav", "aside", "footer", "header"]):
                    tag.decompose()

                text = element.get_text(separator=" ", strip=True)
                text = self._clean_text(text)
                if len(text) >= self.min_text_length:
                    return ExtractedContent(
                        url=url,
                        title=title,
                        text=text,
                        extraction_tier=2,
                        word_count=len(text.split()),
                    )

        return None

    # ── Tier 3: Semantic HTML5 ───────────────────────────────────────────────

    def _try_semantic(
        self, soup: BeautifulSoup, url: str, title: str
    ) -> ExtractedContent | None:
        """Try extraction using HTML5 semantic elements."""
        for selector in SEMANTIC_SELECTORS:
            try:
                element = soup.select_one(selector)
            except Exception:
                continue

            if element is None:
                continue

            # Clean up non-content within semantic element
            for tag in element.find_all(["nav", "aside", "footer"]):
                tag.decompose()

            text = element.get_text(separator=" ", strip=True)
            text = self._clean_text(text)
            if len(text) >= self.min_text_length:
                return ExtractedContent(
                    url=url,
                    title=title,
                    text=text,
                    extraction_tier=3,
                    word_count=len(text.split()),
                )

        return None

    # ── Tier 4: Scored Container ─────────────────────────────────────────────

    def _try_scored(
        self, soup: BeautifulSoup, url: str, title: str
    ) -> ExtractedContent | None:
        """Score containers by text density vs link density, pick best."""
        candidates: list[tuple[float, Tag, str]] = []

        for tag in soup.find_all(["div", "section", "article", "main"]):

            # Skip tiny containers
            text = tag.get_text(separator=" ", strip=True)
            if len(text) < self.min_text_length:
                continue

            # Score: text density penalized by link density
            score = self._score_element(tag)
            if score > 0:
                cleaned = self._clean_text(text)
                candidates.append((score, tag, cleaned))

        if not candidates:
            return None

        # Pick the highest-scoring container
        candidates.sort(key=lambda x: x[0], reverse=True)
        _, _, text = candidates[0]

        return ExtractedContent(
            url=url,
            title=title,
            text=text,
            extraction_tier=4,
            word_count=len(text.split()),
        )

    def _score_element(self, element: Tag) -> float:
        """Score a container by text density.

        Score = len(text) / len(all_text) * (1 - link_text_ratio)
        Higher = more text, fewer links.
        """
        all_text = element.get_text()
        text_len = len(all_text)

        if text_len == 0:
            return 0.0

        # Link penalty: ratio of characters inside <a> tags
        link_text = "".join(a.get_text() for a in element.find_all("a"))
        link_ratio = len(link_text) / text_len if link_text else 0.0

        return text_len * (1.0 - link_ratio)

    # ── Tier 5: Content Elements ─────────────────────────────────────────────

    def _try_elements(
        self, soup: BeautifulSoup, url: str, title: str
    ) -> ExtractedContent | None:
        """Aggregate text from content-bearing elements."""
        body = soup.find("body")
        if body is None:
            return None

        # Remove non-content elements
        for tag in body.find_all(
            ["script", "style", "nav", "footer", "header", "aside", "form"]
        ):
            tag.decompose()

        # Collect content elements
        texts: list[str] = []
        for selector in CONTENT_ELEMENTS:
            for element in body.select(selector):
                text = element.get_text(separator=" ", strip=True)
                if len(text) >= 20:  # skip tiny fragments
                    texts.append(text)

        if not texts:
            return None

        combined = "\n\n".join(texts)
        combined = self._clean_text(combined)
        if len(combined) >= self.min_text_length:
            return ExtractedContent(
                url=url,
                title=title,
                text=combined,
                extraction_tier=5,
                word_count=len(combined.split()),
            )

        return None

    # ── Tier 6: Meta Description ─────────────────────────────────────────────

    def _try_meta(
        self, soup: BeautifulSoup, url: str, title: str
    ) -> ExtractedContent | None:
        """Try meta description and og:description as fallback."""
        meta_text = ""

        for meta in soup.find_all("meta"):
            prop = str(meta.get("property", "")).lower()
            name = str(meta.get("name", "")).lower()
            content = str(meta.get("content", ""))

            if (prop in ("og:description", "twitter:description") or name == "description") and len(content) > len(meta_text):
                    meta_text = content

        meta_text = self._clean_text(meta_text)
        if len(meta_text) >= self.min_text_length:
            return ExtractedContent(
                url=url,
                title=title,
                text=meta_text,
                extraction_tier=6,
                word_count=len(meta_text.split()),
            )

        return None

    # ── Utilities ────────────────────────────────────────────────────────────

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract page title from HTML."""
        # Try og:title first
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            return str(og_title["content"]).strip()

        # Try <title> tag
        title_tag = soup.find("title")
        if title_tag and title_tag.string:
            # Remove site name suffix (after | or -)
            title = title_tag.string.strip()
            for sep in (" | ", " - ", " :: ", " — "):
                if sep in title:
                    # Take the longer part (usually the article title)
                    parts = title.split(sep)
                    title = max(parts, key=len).strip()
            return title

        return ""

    def _clean_text(self, text: str) -> str:
        """Clean extracted text: normalize whitespace, remove boilerplate lines."""
        if not text:
            return ""

        # Normalize whitespace
        text = re.sub(r"\s+", " ", text).strip()

        # Split into lines, filter boilerplate
        sentences = re.split(r"(?<=[.!?])\s+", text)
        filtered = []
        for sentence in sentences:
            if not self._is_boilerplate(sentence):
                filtered.append(sentence)

        return " ".join(filtered).strip()

    def _is_boilerplate(self, text: str) -> bool:
        """Check if a sentence matches boilerplate patterns."""
        return any(re.search(pattern, text) for pattern in BOILERPLATE_PATTERNS)
