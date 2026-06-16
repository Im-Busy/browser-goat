"""Tests for Content Extractor (7-tier cascading)."""

from __future__ import annotations

from browser_goat.extraction.content_extractor import ContentExtractor

SAMPLE_HTML_JSON_LD = """<!DOCTYPE html>
<html><head>
<title>Test Article</title>
<script type="application/ld+json">
{
  "@type": "Article",
  "headline": "JSON-LD Test Article",
  "articleBody": "This is the full article body extracted from JSON-LD structured data."
}
</script>
</head><body><p>Some visible text.</p></body></html>"""

SAMPLE_HTML_CSS = """<!DOCTYPE html>
<html><head><title>CSS Test</title></head>
<body>
<div class="entry-content">
  <p>This is the main article content extracted via CSS selector. It contains enough text to pass the minimum length threshold for content extraction.</p>
</div>
<nav><a href="/">Home</a></nav>
</body></html>"""

SAMPLE_HTML_SEMANTIC = """<!DOCTYPE html>
<html><head><title>Semantic Test</title></head>
<body>
<header>Site header</header>
<article>
  <h1>Article Title</h1>
  <p>The quick brown fox jumps over the lazy dog. This is a test of the semantic HTML5 extraction tier.</p>
</article>
<footer>Site footer</footer>
</body></html>"""

SAMPLE_HTML_META = """<!DOCTYPE html>
<html><head>
<meta name="description" content="Short meta.">
<meta property="og:description" content="OG description is longer and should be preferred as the best summary available for this page with more text.">
</head><body><div class="sidebar">Navigation only</div></body></html>"""


class TestContentExtractor:
    def test_tier1_json_ld(self) -> None:
        extractor = ContentExtractor()
        result = extractor.extract(SAMPLE_HTML_JSON_LD, "https://example.com")
        assert result.extraction_tier == 1
        assert "JSON-LD Test Article" in result.title
        assert "full article body" in result.text

    def test_tier2_css_selectors(self) -> None:
        extractor = ContentExtractor()
        result = extractor.extract(SAMPLE_HTML_CSS, "https://example.com")
        assert result.extraction_tier == 2
        assert "main article content" in result.text

    def test_tier3_semantic(self) -> None:
        extractor = ContentExtractor()
        result = extractor.extract(SAMPLE_HTML_SEMANTIC, "https://example.com")
        assert result.extraction_tier in (3, 4, 5)
        assert "quick brown fox" in result.text

    def test_tier6_meta_fallback(self) -> None:
        extractor = ContentExtractor()
        result = extractor.extract(SAMPLE_HTML_META, "https://example.com")
        assert result.extraction_tier == 6
        assert "OG description" in result.text

    def test_empty_html(self) -> None:
        extractor = ContentExtractor()
        result = extractor.extract("", "https://example.com")
        assert result.extraction_tier == 0
        assert result.text == ""

    def test_extract_title_from_og(self) -> None:
        extractor = ContentExtractor()
        html = '<html><head><meta property="og:title" content="OG Title"></head><body></body></html>'
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        title = extractor._extract_title(soup)
        assert title == "OG Title"

    def test_clean_text_filters_boilerplate(self) -> None:
        extractor = ContentExtractor()
        text = "Great content here. Cookie consent notice. More great content. Subscribe to our newsletter. Final thoughts."
        cleaned = extractor._clean_text(text)
        assert "Great content" in cleaned
        assert "Cookie consent" not in cleaned
        assert "subscribe to our" not in cleaned.lower()

    def test_score_element_text_vs_links(self) -> None:
        extractor = ContentExtractor()
        from bs4 import BeautifulSoup
        html = '<div><p>Good content here with lots of text.</p><a href="/">just a link</a></div>'
        soup = BeautifulSoup(html, "lxml")
        div = soup.find("div")
        score = extractor._score_element(div)
        assert score > 0
