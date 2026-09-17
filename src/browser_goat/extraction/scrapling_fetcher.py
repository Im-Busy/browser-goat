"""Scrapling Fetcher — anti-bot page fetching with progressive escalation.

Tier 1: httpx with browser profile (fastest, ~2s)
Tier 2: Scrapling stealth mode (~5s)
Tier 3: Scrapling with CF Turnstile solving (~15s)
Tier 4: Crawl4AI with optional proxy rotation and Shadow DOM flattening
Tier 5: Playwright headless browser
Tier 6: Plain httpx fallback (~1s)

Ported from scraper-in-one's ScrapeRouter pattern; Crawl4AI tier added
in v0.2.0 for auto anti-bot detection, Shadow DOM flattening, and
memory-monitored browser recycling.
"""

from __future__ import annotations

import asyncio
import os
import time
import urllib.parse
from collections.abc import Awaitable, Callable

import httpx

from browser_goat.extraction.response_acceptance import accept_response
from browser_goat.models import BrowserProfile, FetchResult

# Maximum time a single tier may block before the next tier is attempted.
TIER_BUDGET_SECONDS = 15.0


def _validate_url(url: str) -> tuple[bool, str]:
    """Validate URL syntactically before any network call.

    This is the early-exit gate that prevents the 6-tier cascade from
    burning 14-60s on obviously-invalid inputs like "not-a-url".

    Returns (ok, error_message).
    """
    if not url or not isinstance(url, str):
        return False, "url must be a non-empty string"
    try:
        parsed = urllib.parse.urlparse(url)
    except (ValueError, TypeError) as exc:
        return False, f"malformed url: {exc}"
    if parsed.scheme not in ("http", "https"):
        return False, f"unsupported scheme {parsed.scheme!r}; must be http:// or https://"
    if not parsed.hostname:
        return False, "missing hostname"
    try:
        _ = parsed.port
    except ValueError as exc:
        return False, f"invalid port: {exc}"
    return True, ""


class ScraplingFetcher:
    """Fetch page content with progressive anti-bot escalation.

    Tries the fastest approach first, escalates only on failure.
    """

    def __init__(
        self,
        timeout: float = 30.0,
        max_retries: int = 2,
        proxy_pool: list[str] | None = None,
        enable_crawl4ai: bool = True,
    ) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self.proxy_pool = (
            proxy_pool
            if proxy_pool is not None
            else [
                p.strip()
                for p in os.environ.get("CRAWL4AI_PROXY_LIST", "").split(",")
                if p.strip()
            ]
        )
        self.enable_crawl4ai = enable_crawl4ai
        self._client: httpx.AsyncClient | None = None
        self._crawl4ai_round_robin = 0

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

        # ── Early-exit gate (Bug #1 fix) ─────────────────────────────────────
        # Validate the URL syntactically before any network call. This
        # prevents the 6-tier cascade from burning 14-60s on invalid input.
        ok, err = _validate_url(url)
        if not ok:
            return FetchResult(
                url=url,
                success=False,
                error=err,
                fetch_tier=0,
                latency_ms=int((time.monotonic() - start) * 1000),
            )

        # Create each coroutine only when its tier is reached.
        tiers: list[tuple[int, Callable[[], Awaitable[FetchResult]]]] = [
            (1, lambda: self._try_httpx(url, browser_profile)),
            (2, lambda: self._try_scrapling(url, stealth=True)),
            (3, lambda: self._try_scrapling(url, stealth=True, cf_bypass=True)),
        ]
        if self.enable_crawl4ai:
            tiers.append((4, lambda: self._try_crawl4ai(url)))
        tiers.extend([(5, lambda: self._try_playwright(url)), (6, lambda: self._try_httpx(url, None))])
        for tier, fetch in tiers:
            result = accept_response(await self._bounded_tier(url, fetch()))
            result.fetch_tier = tier
            result.latency_ms = int((time.monotonic() - start) * 1000)
            if result.success:
                result.used_scrapling = tier in (2, 3)
                result.used_crawl4ai = tier == 4
                return result
        return result

    async def _bounded_tier(self, url: str, fetch: Awaitable[FetchResult]) -> FetchResult:
        """Bound a tier, including its retry sleeps, without swallowing cancellation."""
        try:
            return await asyncio.wait_for(fetch, timeout=min(self.timeout, TIER_BUDGET_SECONDS))
        except TimeoutError:
            return FetchResult(url=url, error="Fetch tier timed out")

    async def _try_httpx(
        self, url: str, profile: BrowserProfile | None
    ) -> FetchResult:
        """Try fetching with httpx, optionally with browser profile headers."""
        client = await self._get_client()
        headers = self._build_headers(profile)

        for attempt in range(self.max_retries + 1):
            try:
                response = await client.get(url, headers=headers)
                if 200 <= response.status_code < 300:
                    return accept_response(FetchResult(
                        url=url,
                        html=response.text,
                        status_code=response.status_code,
                        success=True,
                    ))
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
            from scrapling.fetchers import StealthyFetcher
        except ImportError:
            return FetchResult(url=url, success=False, error="scrapling fetcher dependencies not installed")

        try:
            page = await StealthyFetcher.async_fetch(
                url, headless=True, solve_cloudflare=cf_bypass,
                timeout=int(self.timeout * 1000),
            )

            if page is not None and 200 <= page.status < 300:
                return accept_response(FetchResult(
                    url=url,
                    html=page.body.decode("utf-8", errors="replace"),
                    status_code=page.status,
                    success=True,
                    used_scrapling=True,
                ))

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

    async def _try_crawl4ai(self, url: str) -> FetchResult:
        """Fetch with Crawl4AI's Shadow DOM flattening and optional round-robin proxy."""
        try:
            from crawl4ai import (  # type: ignore[import-untyped]  # upstream has no typing marker
                AsyncWebCrawler,
                BrowserConfig,
                CrawlerRunConfig,
            )
        except ImportError:
            return FetchResult(url=url, success=False, error="crawl4ai not installed")

        proxy = None
        if self.proxy_pool:
            proxy = self.proxy_pool[self._crawl4ai_round_robin % len(self.proxy_pool)]
            self._crawl4ai_round_robin += 1

        try:
            config = CrawlerRunConfig(
                flatten_shadow_dom=True, proxy_config=proxy,
                page_timeout=int(self.timeout * 1000), verbose=False,
            )
            async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
                result = await crawler.arun(url=url, config=config)

            html = getattr(result, "html", None) or getattr(result, "content", None)
            status = getattr(result, "status_code", None) or 0
            success = getattr(result, "success", bool(html))

            if success:
                return accept_response(FetchResult(
                    url=url,
                    html=str(html or ""),
                    status_code=int(status),
                    success=True,
                ))

            return FetchResult(
                url=url,
                status_code=int(status) if status else 0,
                success=False,
                error="Crawl4AI returned no usable content",
            )
        except Exception as exc:
            return FetchResult(
                url=url,
                success=False,
                error=f"Crawl4AI error: {exc}",
            )

    async def _try_playwright(self, url: str) -> FetchResult:
        """Try fetching with Playwright headless browser (last resort)."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return FetchResult(url=url, success=False, error="playwright not installed")

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                try:
                    page = await browser.new_page()
                    response = await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout * 1000)
                    html = await page.content()
                    status = response.status if response is not None else 0
                finally:
                    await browser.close()
                return accept_response(FetchResult(
                    url=url,
                    html=html,
                    status_code=status,
                    success=True,
                ))
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
                "User-Agent": "Mozilla/5.0 (compatible; BrowserGoat/0.1)",
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
