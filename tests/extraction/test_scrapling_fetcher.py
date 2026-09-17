"""Tests for Scrapling Fetcher — anti-bot page fetching with progressive escalation."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from browser_goat.extraction.scrapling_fetcher import ScraplingFetcher
from browser_goat.models import BrowserProfile, FetchResult


class TestScraplingFetcher:
    """Test suite for ScraplingFetcher progressive escalation fetcher."""

    @pytest.fixture
    def fetcher(self) -> ScraplingFetcher:
        """Create a ScraplingFetcher with short timeout for fast tests."""
        return ScraplingFetcher(timeout=10.0, max_retries=1)

    @pytest.fixture
    def sample_profile(self) -> BrowserProfile:
        """Create a sample browser profile for header tests."""
        return BrowserProfile(
            name="Chrome 147 Windows",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/147.0.0.0 Safari/537.36"
            ),
            sec_ch_ua='"Google Chrome";v="147", "Not;A=Brand";v="24"',
            sec_ch_ua_platform='"Windows"',
            sec_ch_ua_mobile="?0",
        )

    # ── Test 1: Tier 1 (httpx) success ──────────────────────────────

    @patch("browser_goat.extraction.scrapling_fetcher.httpx.AsyncClient")
    async def test_fetch_tier1_success(
        self, mock_client_cls: MagicMock, fetcher: ScraplingFetcher
    ) -> None:
        """fetch() should succeed at Tier 1 when httpx returns 200."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html><body>Hello World</body></html>"
        mock_client.get = AsyncMock(return_value=mock_response)

        result = await fetcher.fetch("https://example.com")

        assert result.success is True
        assert result.status_code == 200
        assert result.html == "<html><body>Hello World</body></html>"
        assert result.url == "https://example.com"
        assert result.fetch_tier == 1
        assert result.used_scrapling is False
        assert result.error is None
        assert result.latency_ms >= 0

    # ── Test 2: FetchResult field correctness ───────────────────────

    @patch("browser_goat.extraction.scrapling_fetcher.httpx.AsyncClient")
    async def test_fetch_result_fields(
        self, mock_client_cls: MagicMock, fetcher: ScraplingFetcher
    ) -> None:
        """fetch() should return a properly structured FetchResult model."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html>Data</html>"
        mock_client.get = AsyncMock(return_value=mock_response)

        result = await fetcher.fetch("https://example.org/page")

        assert isinstance(result, FetchResult)
        assert result.url == "https://example.org/page"
        assert result.html == "<html>Data</html>"
        assert result.status_code == 200
        assert result.success is True
        assert result.fetch_tier == 1
        assert result.used_scrapling is False
        assert result.error is None

    # ── Test 3: Connection error handling ───────────────────────────

    @patch("browser_goat.extraction.scrapling_fetcher.httpx.AsyncClient")
    async def test_fetch_connection_error(
        self, mock_client_cls: MagicMock, fetcher: ScraplingFetcher
    ) -> None:
        """fetch() should gracefully handle network errors and fall through to Tier 6."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=ConnectionError("Connection refused"))

        with (
            patch("browser_goat.extraction.scrapling_fetcher.asyncio.sleep", AsyncMock()),
            patch.object(fetcher, "_try_scrapling") as mock_scrapling,
            patch.object(fetcher, "_try_crawl4ai") as mock_c4ai,
            patch.object(fetcher, "_try_playwright") as mock_pw,
        ):
            mock_scrapling.return_value = FetchResult(
                url="https://example.com", success=False, error="scrapling failed"
            )
            mock_c4ai.return_value = FetchResult(
                url="https://example.com", success=False, error="crawl4ai failed"
            )
            mock_pw.return_value = FetchResult(
                url="https://example.com", success=False, error="playwright failed"
            )

            result = await fetcher.fetch("https://example.com")

        assert result.success is False
        assert result.error is not None
        assert "Connection refused" in result.error
        assert result.fetch_tier == 6
        assert result.latency_ms >= 0

    # ── Test 4: Progressive escalation L1 → L2 ──────────────────────

    async def test_escalation_tier1_fails_tier2_succeeds(
        self, fetcher: ScraplingFetcher
    ) -> None:
        """fetch() should escalate to Tier 2 (scrapling) when Tier 1 fails with 403."""
        with (
            patch.object(fetcher, "_try_httpx") as mock_httpx,
            patch.object(fetcher, "_try_scrapling") as mock_scrapling,
        ):
            mock_httpx.return_value = FetchResult(
                url="https://example.com",
                status_code=403,
                success=False,
                error="HTTP 403",
            )
            mock_scrapling.return_value = FetchResult(
                url="https://example.com",
                html="<html>Scrapling content</html>",
                status_code=200,
                success=True,
                used_scrapling=True,
            )

            result = await fetcher.fetch("https://example.com")

            assert result.success is True
            assert result.fetch_tier == 2
            assert result.used_scrapling is True
            assert "Scrapling content" in result.html
            mock_httpx.assert_called_once_with("https://example.com", None)
            mock_scrapling.assert_called_once_with("https://example.com", stealth=True)

    # ── Test 5: Browser profile → header building ───────────────────

    def test_build_headers_with_browser_profile(
        self, fetcher: ScraplingFetcher, sample_profile: BrowserProfile
    ) -> None:
        """_build_headers() should emit Sec-CH-UA headers from the profile."""
        headers = fetcher._build_headers(sample_profile)

        assert headers["User-Agent"] == sample_profile.user_agent
        assert headers["Accept"] == sample_profile.accept
        assert headers["Accept-Language"] == sample_profile.accept_language
        assert headers["Accept-Encoding"] == sample_profile.accept_encoding
        assert headers["Sec-CH-UA"] == sample_profile.sec_ch_ua
        assert headers["Sec-CH-UA-Platform"] == sample_profile.sec_ch_ua_platform
        assert headers["Sec-CH-UA-Mobile"] == sample_profile.sec_ch_ua_mobile

    def test_build_headers_without_profile(
        self, fetcher: ScraplingFetcher
    ) -> None:
        """_build_headers() with no profile returns minimal headers only."""
        headers = fetcher._build_headers(None)

        assert "User-Agent" in headers
        assert "Accept" in headers
        assert "Sec-CH-UA" not in headers
        assert "Sec-CH-UA-Platform" not in headers

    # ── Test 6: Retry on HTTP 403 then succeed ──────────────────────

    @patch("browser_goat.extraction.scrapling_fetcher.httpx.AsyncClient")
    async def test_try_httpx_retry_on_403(
        self, mock_client_cls: MagicMock, fetcher: ScraplingFetcher
    ) -> None:
        """_try_httpx() should retry on 403 and return success on subsequent attempt."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        resp_403 = MagicMock(status_code=403, text="")
        resp_200 = MagicMock(status_code=200, text="<html>Retry success</html>")
        mock_client.get = AsyncMock(side_effect=[resp_403, resp_200])

        with patch("browser_goat.extraction.scrapling_fetcher.asyncio.sleep", AsyncMock()):
            result = await fetcher._try_httpx("https://example.com", None)

        assert result.success is True
        assert result.html == "<html>Retry success</html>"
        assert result.status_code == 200
        assert mock_client.get.call_count == 2

    # ── Test 7: _try_scrapling handles ImportError gracefully ────

    async def test_try_scrapling_not_installed(
        self, fetcher: ScraplingFetcher
    ) -> None:
        """_try_scrapling() should return error result when scrapling is not available."""
        with patch.dict(sys.modules, {"scrapling": None, "scrapling.fetchers": None}):
            result = await fetcher._try_scrapling("https://example.com")

        assert result.success is False
        assert "scrapling" in result.error.lower()

    # ── Test 8: URL validation gate — malformed URL returns tier=0 fast ──

    @pytest.mark.parametrize(
        "bad_url,expected_substring",
        [
            ("not-a-url", "unsupported scheme"),
            ("", "non-empty string"),
            ("ftp://example.com", "unsupported scheme"),
            ("http://", "missing hostname"),
            ("123", "unsupported scheme"),  # str(123) == "123" → scheme=""
        ],
    )
    async def test_bad_url_returns_tier0_under_100ms(
        self,
        fetcher: ScraplingFetcher,
        bad_url: object,
        expected_substring: str,
    ) -> None:
        """Malformed URLs must be rejected synchronously at tier 0, not cascaded.

        This guards against regression of the 60-second MCP timeout that
        occurred when the 6-tier cascade was entered with an obviously-invalid
        URL. Each malformed URL should return in < 100 ms with fetch_tier=0.
        """
        import time

        t0 = time.monotonic()
        result = await fetcher.fetch(str(bad_url))  # type: ignore[arg-type]
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        assert result.success is False
        assert result.fetch_tier == 0, f"expected tier 0, got {result.fetch_tier}"
        assert expected_substring in (result.error or "")
        assert elapsed_ms < 100, f"took {elapsed_ms} ms; expected < 100 ms"

    async def test_validate_url_standalone(self) -> None:
        """_validate_url() should categorise all error cases correctly."""
        from browser_goat.extraction.scrapling_fetcher import _validate_url

        ok, err = _validate_url("https://example.com")
        assert ok is True
        assert err == ""

        ok, err = _validate_url("not-a-url")
        assert ok is False
        assert "unsupported scheme" in err

        ok, err = _validate_url("")
        assert ok is False
        assert "non-empty string" in err

        ok, err = _validate_url("ftp://x.com")
        assert ok is False
        assert "unsupported scheme" in err

        ok, err = _validate_url("http://")
        assert ok is False
        assert "missing hostname" in err


async def test_scrapling_adapter_decodes_body_and_enables_challenge_solver() -> None:
    async_fetch = AsyncMock(return_value=SimpleNamespace(status=200, body=b"<p>Python</p>"))
    module = SimpleNamespace(StealthyFetcher=SimpleNamespace(async_fetch=async_fetch))
    with patch.dict(sys.modules, {"scrapling.fetchers": module}):
        result = await ScraplingFetcher(timeout=2)._try_scrapling("https://example.com", cf_bypass=True)
    assert result.success and result.html == "<p>Python</p>"
    assert async_fetch.call_args.kwargs["solve_cloudflare"] is True
    assert async_fetch.call_args.kwargs["timeout"] == 2000


async def test_crawl4ai_uses_supported_installed_config() -> None:
    from crawl4ai import CrawlerRunConfig

    captured = []

    async def arun(*, url: str, config: object) -> object:
        captured.append(config)
        return SimpleNamespace(html="<p>Python</p>", success=True, status_code=200)

    crawler = AsyncMock()
    crawler.arun.side_effect = arun
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=crawler)
    manager.__aexit__ = AsyncMock(return_value=False)
    with patch("crawl4ai.AsyncWebCrawler", return_value=manager):
        result = await ScraplingFetcher(proxy_pool=["http://127.0.0.1:9999"])._try_crawl4ai("https://example.com")
    assert result.success
    assert isinstance(captured[0], CrawlerRunConfig)
    assert captured[0].flatten_shadow_dom is True
    assert captured[0].proxy_config.server == "http://127.0.0.1:9999"


async def test_tier_timeout_cancels_operation() -> None:
    import asyncio

    cancelled = asyncio.Event()

    async def slow() -> FetchResult:
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.set()
        return FetchResult(url="https://example.com")

    result = await ScraplingFetcher(timeout=0.01)._bounded_tier("https://example.com", slow())
    assert not result.success and "timed out" in result.error
    assert cancelled.is_set()
