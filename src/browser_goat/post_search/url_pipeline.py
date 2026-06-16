"""URL Pipeline — normalize, blocklist, dedup, strip tracking params.

Ported from SearchWala src/url_utils.rs. Single-pass processing:
one URL parse handles normalize + blocklist + dedup.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from browser_goat.models import CleanedResult, RawSearchResult

# ── Configuration ─────────────────────────────────────────────────────────────

# 30+ tracking parameters to strip
TRACKING_PARAMS: set[str] = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "utm_reader", "ref", "ref_src", "ref_url",
    "fbclid", "gclid", "gclsrc", "dclid", "msclkid",
    "mc_cid", "mc_eid", "mc_mid",
    "oly_anon_id", "oly_enc_id",
    "_openstat", "vero_id", "wickedid", "yclid",
    "igshid", "twclid", "sc_campaign", "sc_channel", "sc_content",
    "sc_medium", "sc_outcome", "sc_geo", "sc_country",
    "si", "hash", "source", "campaign_id",
}

# 15+ domains to skip
SKIP_DOMAINS: set[str] = {
    "pinterest.com", "pinterest.ca", "pinterest.co.uk",
    "quora.com",
    "facebook.com", "fb.com",
    "instagram.com",
    "twitter.com", "x.com",
    "tiktok.com",
    "reddit.com",
    "linkedin.com",
    "amazon.com", "amazon.co.uk",
}

# 14 file extensions to skip
SKIP_EXTENSIONS: set[str] = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".tar", ".gz", ".rar", ".7z",
    ".mp4", ".avi", ".mov", ".mkv", ".webm",
    ".mp3", ".wav", ".flac",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg",
}


class URLPipeline:
    """Process search results: normalize URLs, strip tracking params,
    remove blocked domains, and deduplicate.
    """

    def __init__(
        self,
        skip_domains: set[str] | None = None,
        skip_extensions: set[str] | None = None,
        tracking_params: set[str] | None = None,
    ) -> None:
        self.skip_domains = skip_domains or SKIP_DOMAINS
        self.skip_extensions = skip_extensions or SKIP_EXTENSIONS
        self.tracking_params = tracking_params or TRACKING_PARAMS

    def process(self, results: list[RawSearchResult]) -> list[CleanedResult]:
        """Single-pass pipeline: normalize, filter, dedup.

        Returns cleaned, deduplicated results with normalized URLs.
        """
        seen: set[str] = set()
        cleaned: list[CleanedResult] = []

        for result in results:
            normalized = self._normalize_url(result.url)

            # Check blocklists
            if self._should_skip(normalized):
                cleaned.append(
                    CleanedResult(
                        **result.model_dump(),
                        normalized_url=normalized,
                        is_duplicate=False,
                        blocked_reason="blocked_domain_or_extension",
                    )
                )
                continue

            # Deduplicate by host+path
            dedup_key = self._dedup_key(normalized)
            if dedup_key in seen:
                cleaned.append(
                    CleanedResult(
                        **result.model_dump(),
                        normalized_url=normalized,
                        is_duplicate=True,
                    )
                )
                continue

            seen.add(dedup_key)
            cleaned.append(
                CleanedResult(
                    **result.model_dump(),
                    normalized_url=normalized,
                    is_duplicate=False,
                )
            )

        return cleaned

    def _normalize_url(self, url: str) -> str:
        """Normalize a URL: lowercase host, remove fragment, strip tracking params.

        Returns the original URL if parsing fails.
        """
        try:
            parsed = urlparse(url)
        except Exception:
            return url

        # Lowercase the hostname
        netloc = parsed.netloc.lower()

        # Remove fragment
        fragment = ""

        # Strip tracking parameters from query string
        query = self._strip_tracking_params(parsed.query)

        # Reconstruct URL
        normalized = urlunparse(
            (parsed.scheme, netloc, parsed.path, parsed.params, query, fragment)
        )
        return normalized

    def _strip_tracking_params(self, query_string: str) -> str:
        """Remove known tracking parameters from a query string."""
        if not query_string:
            return ""

        params = parse_qs(query_string, keep_blank_values=False)
        filtered = {
            k: v for k, v in params.items()
            if k.lower() not in self.tracking_params
        }
        return urlencode(filtered, doseq=True)

    def _should_skip(self, url: str) -> bool:
        """Check if URL should be skipped based on domain or extension blocklists."""
        try:
            parsed = urlparse(url)
        except Exception:
            return True  # Skip unparseable URLs

        hostname = parsed.netloc.lower()

        # Check domain blocklist
        for domain in self.skip_domains:
            if hostname == domain or hostname.endswith("." + domain):
                return True

        # Check extension blocklist
        path_lower = parsed.path.lower()
        return any(path_lower.endswith(ext) for ext in self.skip_extensions)

    def _dedup_key(self, url: str) -> str:
        """Generate a deduplication key from hostname + path.

        Two URLs are considered duplicates if they have the same hostname
        and path (ignoring query parameters for query-bearing URLs).
        """
        try:
            parsed = urlparse(url)
        except Exception:
            return url

        host = parsed.netloc.lower()
        path = parsed.path.rstrip("/")

        # For URLs with query strings, include them in the key
        if parsed.query:
            return f"{host}{path}?{parsed.query}"

        return f"{host}{path}"
