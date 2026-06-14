"""Scrapling Fetcher — anti-bot page fetching with progressive escalation.

Tier 1: httpx with browser profile (fastest, ~2s)
Tier 2: Scrapling stealth mode (~5s)
Tier 3: Scrapling with CF Turnstile solving (~15s)
Tier 4: Playwright headful browser (~30s)
Tier 5: Plain httpx fallback (~1s)

Ported from scraper-in-one's ScrapeRouter pattern.
"""

from __future__ import annotations

import asyncio
import time

import httpx

from browsing_meta.models import BrowserProfile, FetchResult


class ScraplingFetcher:
    """Fetch page content with progressive anti-bot escalation.

    Tries the fastest approach first, escalates only on failure.
    """

    def __init__(
        self,
        timeout: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
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

    async def fetch(
        self,
        url: str,
        browser_profile: BrowserProfile | None = None,
    ) -> FetchResult:
        """Fetch page content with progressive escalation.

        Args:
            url: The URL to fetch.
            browser_profile: Optional browser profile for stealth headers.

        Returns:
            FetchResult with HTML content, status code, and tier info.
        """
        start = time.monotonic()

        # Tier 1: httpx with browser profile headers
        result = await self._try_httpx(url, browser_profile)
        if result.success:
            result.fetch_tier = 1
            result.latency_ms = int((time.monotonic() - start) * 1000)
            return result

        # Tier 2: Scrapling stealth mode
        result = await self._try_scrapling(url, stealth=True)
        if result.success:
            result.used_scrapling = True
            result.fetch_tier = 2
            result.latency_ms = int((time.monotonic() - start) * 1000)
            return result

        # Tier 3: Scrapling with CF Turnstile
        result = await self._try_scrapling(url, stealth=True, cf_bypass=True)
        if result.success:
            result.used_scrapling = True
            result.fetch_tier = 3
            result.latency_ms = int((time.monotonic() - start) * 1000)
            return result

        # Tier 4: Playwright headful
        result = await self._try_playwright(url)
        if result.success:
            result.fetch_tier = 4
            result.latency_ms = int((time.monotonic() - start) * 1000)
            return result

        # Tier 5: Plain httpx (no profile)
        result = await self._try_httpx(url, None)
        result.fetch_tier = 5
        result.latency_ms = int((time.monotonic() - start) * 1000)
        return result

    async def _try_httpx(
        self, url: str, profile: BrowserProfile | None
    ) -> FetchResult:
        """Try fetching with httpx, optionally with browser profile headers."""
        client = await self._get_client()
        headers = self._build_headers(profile)

        for attempt in range(self.max_retries + 1):
            try:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    return FetchResult(
                        url=url,
                        html=response.text,
                        status_code=200,
                        success=True,
                    )
                elif response.status_code in (403, 429, 503):
                    if attempt < self.max_retries:
                        await asyncio.sleep(1 * (attempt + 1))
                        continue
                    return FetchResult(
                        url=url,
                        status_code=response.status_code,
                        success=False,
                        error=f"HTTP {response.status_code}",
                    )
                else:
                    return FetchResult(
                        url=url,
                        status_code=response.status_code,
                        success=False,
                        error=f"HTTP {response.status_code}",
                    )
            except Exception as exc:
                if attempt < self.max_retries:
                    await asyncio.sleep(1 * (attempt + 1))
                    continue
                return FetchResult(
                    url=url,
                    success=False,
                    error=str(exc),
                )

        return FetchResult(url=url, success=False, error="max retries exceeded")

    async def _try_scrapling(
        self,
        url: str,
        stealth: bool = False,
        cf_bypass: bool = False,
    ) -> FetchResult:
        """Try fetching with Scrapling anti-bot bypass.

        Uses Scrapling's StealthyFetcher for browser impersonation
        and Cloudflare Turnstile solving.
        """
        try:
            from scrapling import StealthyFetcher  # type: ignore[import-untyped,unused-ignore]
        except ImportError:
            return FetchResult(url=url, success=False, error="scrapling not installed")

        try:
            fetcher = StealthyFetcher(auto_match=False)  # type: ignore[no-untyped-call]
            page = await fetcher.async_fetch(url)  # type: ignore[attr-defined,unused-ignore]

            if page and page.status == 200:
                return FetchResult(
                    url=url,
                    html=str(page.content),  # type: ignore[attr-defined]
                    status_code=200,
                    success=True,
                    used_scrapling=True,
                )

            return FetchResult(
                url=url,
                status_code=page.status if page else 0,
                success=False,
                error=f"Scrapling returned status {page.status if page else 'unknown'}",
            )
        except Exception as exc:
            return FetchResult(
                url=url,
                success=False,
                error=f"Scrapling error: {exc}",
            )

    async def _try_playwright(self, url: str) -> FetchResult:
        """Try fetching with Playwright headful browser (last resort)."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return FetchResult(url=url, success=False, error="playwright not installed")

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout * 1000)
                html = await page.content()
                await browser.close()
                return FetchResult(
                    url=url,
                    html=html,
                    status_code=200,
                    success=True,
                )
        except Exception as exc:
            return FetchResult(
                url=url,
                success=False,
                error=f"Playwright error: {exc}",
            )

    def _build_headers(self, profile: BrowserProfile | None) -> dict[str, str]:
        """Build headers dict from browser profile."""
        if profile is None:
            return {
                "User-Agent": "Mozilla/5.0 (compatible; BrowsingMeta/0.1)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }

        headers: dict[str, str] = {
            "User-Agent": profile.user_agent,
            "Accept": profile.accept,
            "Accept-Language": profile.accept_language,
            "Accept-Encoding": profile.accept_encoding,
            "Sec-CH-UA": profile.sec_ch_ua,
        }
        if profile.sec_ch_ua_platform:
            headers["Sec-CH-UA-Platform"] = profile.sec_ch_ua_platform
        if profile.sec_ch_ua_mobile:
            headers["Sec-CH-UA-Mobile"] = profile.sec_ch_ua_mobile
        return headers
