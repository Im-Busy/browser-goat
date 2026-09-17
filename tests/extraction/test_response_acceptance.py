"""HTTP 200 alone must not suppress browser escalation or poison the HTML cache."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from browser_goat.extraction.scrapling_fetcher import ScraplingFetcher
from browser_goat.models import FetchResult
from browser_goat.router import BrowserGoat

CHALLENGES = [
    "", " \n\t ", "<html><body></body></html>",
    "<html><title>Just a moment...</title><body><form id='challenge-form'>Checking your browser</form></body></html>",
    "<html><title>Security check</title><body>Please verify you are human<div class='g-recaptcha'></div></body></html>",
    "<html><body><noscript>You need to enable JavaScript to run this app.</noscript><div id='root'></div></body></html>",
]


@pytest.mark.parametrize("html", CHALLENGES)
async def test_httpx_rejects_empty_or_challenge_html(html: str) -> None:
    fetcher = ScraplingFetcher(max_retries=0)
    client = MagicMock(get=AsyncMock(return_value=MagicMock(status_code=200, text=html)))
    with patch.object(fetcher, "_get_client", AsyncMock(return_value=client)):
        result = await fetcher._try_httpx("https://example.com", None)
    assert not result.success and result.error


@pytest.mark.parametrize("html", [
    "<article><h1>CAPTCHA documentation</h1><p>Enable JavaScript to use a CAPTCHA widget. Cloudflare challenge examples.</p></article>",
    "<article><h1>JavaScript guide</h1><pre>&lt;form id='challenge-form'&gt;Verify you are human&lt;/form&gt;</pre></article>",
    "<main><h1>Python</h1><p>Event loop reference.</p></main><noscript>Please enable JavaScript</noscript>",
    "<html><title>CAPTCHA</title><main><h1>CAPTCHA</h1><p>Reference material about verification widgets.</p></main></html>",
    "<html><body><p>Hello</p></body></html>",
    "<p>Enable JavaScript to use a CAPTCHA widget. See our configuration documentation.</p>",
    '<script type="application/ld+json">' + json.dumps({"articleBody": "Python asyncio reference. " * 10}) + '</script>',
    '<meta name="description" content="' + "Python asyncio reference. " * 10 + '">',
])
async def test_documentation_not_rejected_for_challenge_vocabulary(html: str) -> None:
    fetcher = ScraplingFetcher(max_retries=0)
    client = MagicMock(get=AsyncMock(return_value=MagicMock(status_code=200, text=html)))
    with patch.object(fetcher, "_get_client", AsyncMock(return_value=client)):
        result = await fetcher._try_httpx("https://example.com", None)
    assert result.success


@pytest.mark.parametrize("tier", [1, 2, 3, 4, 5, 6])
async def test_no_tier_accepts_and_caches_a_challenge(tier: int) -> None:
    goat = BrowserGoat()

    calls = 0

    async def attempt() -> FetchResult:
        nonlocal calls
        calls += 1
        return FetchResult(url="https://example.com", status_code=200,
                           success=calls == tier, html=CHALLENGES[3])

    with (
        patch.object(goat.scrapling, "_try_httpx", AsyncMock()) as httpx,
        patch.object(goat.scrapling, "_try_scrapling", AsyncMock()) as scrapling,
        patch.object(goat.scrapling, "_try_crawl4ai", AsyncMock()) as crawl4ai,
        patch.object(goat.scrapling, "_try_playwright", AsyncMock()) as playwright,
    ):
        async def invoke(*args: object, **kwargs: object) -> FetchResult:
            return await attempt()

        for mock in (httpx, scrapling, crawl4ai, playwright):
            mock.side_effect = invoke
        result = await goat._fetch_with_cache("https://example.com", None)
    assert not result.success
    assert calls == 6
    assert goat.cache_stats()["size"] == 0


async def test_challenge_escalates_to_usable_content() -> None:
    fetcher = ScraplingFetcher()
    with (
        patch.object(fetcher, "_try_httpx", AsyncMock(return_value=FetchResult(
            url="https://example.com", status_code=200, success=True, html=CHALLENGES[3],
        ))),
        patch.object(fetcher, "_try_scrapling", AsyncMock(return_value=FetchResult(
            url="https://example.com", status_code=200, success=True, html="<p>Python documentation.</p>",
        ))),
    ):
        result = await fetcher.fetch("https://example.com")
    assert result.success and result.fetch_tier == 2
