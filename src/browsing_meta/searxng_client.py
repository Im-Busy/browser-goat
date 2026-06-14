"""Async SearXNG client using the JSON API."""

from __future__ import annotations

from typing import Any

import httpx

from browsing_meta.models import (
    BrowserProfile,
    LanguageParams,
    RawSearchResult,
)


class SearXNGClient:
    """Async HTTP client for SearXNG's JSON search API.

    Usage:
        client = SearXNGClient("http://localhost:8080")
        results = await client.search("what is python?")

    Integrates browser profile headers and language-aware parameters
    for stealth and localization.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        timeout: float = 15.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=True,
                http2=True,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def search(
        self,
        query: str,
        engines: list[str] | None = None,
        categories: list[str] | None = None,
        language: str = "en",
        time_range: str | None = None,
        page: int = 1,
        safe_search: int = 0,
        browser_profile: BrowserProfile | None = None,
        lang_params: LanguageParams | None = None,
    ) -> list[RawSearchResult]:
        """Execute a search against SearXNG and return parsed results.

        Args:
            query: Search query string.
            engines: List of engine names (e.g. ["google", "bing"]).
            categories: SearXNG categories (e.g. ["general", "news"]).
            language: Language code for results.
            time_range: Time filter: day, week, month, year.
            page: Result page number (1-indexed).
            safe_search: Safe search level (0=none, 1=moderate, 2=strict).
            browser_profile: Optional browser profile for stealth headers.
            lang_params: Optional language-aware location/gl/hl overrides.

        Returns:
            List of RawSearchResult objects parsed from SearXNG JSON.

        Raises:
            httpx.HTTPError: On network or HTTP errors.
            ValueError: On malformed response.
        """
        client = await self._get_client()

        params: dict[str, Any] = {
            "q": query,
            "format": "json",
            "language": language,
            "pageno": page,
            "safesearch": safe_search,
        }

        if engines:
            params["engines"] = ",".join(engines)
        if categories:
            params["categories"] = ",".join(categories)
        if time_range:
            params["time_range"] = time_range

        # Apply language-aware parameters via SearXNG's accepted format
        if lang_params:
            params["language"] = lang_params.hl

        headers = self._build_headers(browser_profile)

        try:
            response = await client.get(
                f"{self.base_url}/search",
                params=params,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError:
            raise
        except Exception as exc:
            raise ValueError(f"Failed to parse SearXNG response: {exc}") from exc

        return self._parse_results(data)

    def _build_headers(
        self, browser_profile: BrowserProfile | None
    ) -> dict[str, str]:
        """Build request headers with optional browser profile."""
        headers: dict[str, str] = {}
        if browser_profile is None:
            return headers

        headers["User-Agent"] = browser_profile.user_agent
        headers["Accept"] = browser_profile.accept
        headers["Accept-Language"] = browser_profile.accept_language
        headers["Accept-Encoding"] = browser_profile.accept_encoding
        headers["Sec-CH-UA"] = browser_profile.sec_ch_ua
        headers["Sec-CH-UA-Platform"] = browser_profile.sec_ch_ua_platform
        headers["Sec-CH-UA-Mobile"] = browser_profile.sec_ch_ua_mobile
        return headers

    def _parse_results(self, data: dict[str, Any]) -> list[RawSearchResult]:
        """Parse SearXNG JSON response into RawSearchResult list.

        SearXNG JSON format:
        {
            "query": "...",
            "number_of_results": 123,
            "results": [
                {
                    "title": "...",
                    "url": "...",
                    "content": "...",
                    "engine": "google",
                    "score": 0.0,
                    "category": "general",
                    "parsed_url": ["...", ...],
                    "publishedDate": "2026-06-14"
                }
            ]
        }
        """
        raw_results = data.get("results", [])
        if not isinstance(raw_results, list):
            return []

        parsed: list[RawSearchResult] = []
        for item in raw_results:
            if not isinstance(item, dict):
                continue

            url = item.get("url", "")
            if not url:
                continue

            # parsed_url is either a list of strings or None
            parsed_url_val = item.get("parsed_url")
            if isinstance(parsed_url_val, list) and parsed_url_val:
                parsed_url = str(parsed_url_val[0])
            else:
                parsed_url = url

            parsed.append(
                RawSearchResult(
                    title=item.get("title", ""),
                    url=url,
                    content=item.get("content", ""),
                    engine=item.get("engine", ""),
                    score=float(item.get("score", 0.0)),
                    category=item.get("category", ""),
                    parsed_url=parsed_url,
                    published_date=item.get("publishedDate"),
                )
            )

        return parsed

    async def health_check(self) -> bool:
        """Check if SearXNG instance is reachable."""
        try:
            client = await self._get_client()
            response = await client.get(f"{self.base_url}/health")
            return response.status_code == 200
        except Exception:
            return False
