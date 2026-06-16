"""Tests for browser profiles."""

from __future__ import annotations

from browser_goat.pre_search.browser_profiles import PROFILES, BrowserProfiles


class TestBrowserProfiles:
    def test_profiles_loaded(self) -> None:
        assert len(PROFILES) == 20

    def test_all_profiles_have_required_fields(self) -> None:
        for profile in PROFILES:
            assert profile.name
            assert profile.user_agent
            assert profile.sec_ch_ua

    def test_get_random_profile(self) -> None:
        bp = BrowserProfiles()
        profile = bp.get_random_profile()
        assert profile in PROFILES

    def test_get_random_profile_different(self) -> None:
        bp = BrowserProfiles()
        profiles = {bp.get_random_profile().name for _ in range(100)}
        # Should get multiple different profiles
        assert len(profiles) >= 3

    def test_custom_profile_list(self) -> None:
        bp = BrowserProfiles(profiles=PROFILES[:3])
        profile = bp.get_random_profile()
        assert profile in PROFILES[:3]

    def test_apply_to_headers_explicit_profile(self) -> None:
        bp = BrowserProfiles()
        profile = PROFILES[0]
        headers: dict[str, str] = {}
        result = bp.apply_to_headers(headers, profile)
        assert result["User-Agent"] == profile.user_agent
        assert result["Sec-CH-UA"] == profile.sec_ch_ua

    def test_apply_to_headers_random_profile(self) -> None:
        bp = BrowserProfiles()
        headers: dict[str, str] = {}
        result = bp.apply_to_headers(headers)
        assert "User-Agent" in result
        assert "Sec-CH-UA" in result
