"""Browser profiles for WAF bypass — ported from SearchWala config.rs.

20 realistic browser profiles with matching Sec-CH-UA headers,
rotated per request to reduce bot detection.
"""

from __future__ import annotations

import random

from browser_goat.models import BrowserProfile

# ── 20 Browser Profiles ───────────────────────────────────────────────────────
# Each profile includes coherent User-Agent, Sec-CH-UA, platform, and mobile flag
# matching real browser versions as of 2025-2026.

PROFILES: list[BrowserProfile] = [
    # Chrome 147 on Windows
    BrowserProfile(
        name="Chrome 147 Windows",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
        sec_ch_ua='"Chromium";v="147", "Google Chrome";v="147", "Not:A-Brand";v="99"',
        sec_ch_ua_platform='"Windows"',
        sec_ch_ua_mobile="?0",
    ),
    # Chrome 147 on macOS
    BrowserProfile(
        name="Chrome 147 macOS",
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
        sec_ch_ua='"Chromium";v="147", "Google Chrome";v="147", "Not:A-Brand";v="99"',
        sec_ch_ua_platform='"macOS"',
        sec_ch_ua_mobile="?0",
    ),
    # Chrome 147 on Linux
    BrowserProfile(
        name="Chrome 147 Linux",
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
        sec_ch_ua='"Chromium";v="147", "Google Chrome";v="147", "Not:A-Brand";v="99"',
        sec_ch_ua_platform='"Linux"',
        sec_ch_ua_mobile="?0",
    ),
    # Edge 147 on Windows
    BrowserProfile(
        name="Edge 147 Windows",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36 Edg/147.0.0.0",
        sec_ch_ua='"Chromium";v="147", "Microsoft Edge";v="147", "Not:A-Brand";v="99"',
        sec_ch_ua_platform='"Windows"',
        sec_ch_ua_mobile="?0",
    ),
    # Edge 147 on macOS
    BrowserProfile(
        name="Edge 147 macOS",
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36 Edg/147.0.0.0",
        sec_ch_ua='"Chromium";v="147", "Microsoft Edge";v="147", "Not:A-Brand";v="99"',
        sec_ch_ua_platform='"macOS"',
        sec_ch_ua_mobile="?0",
    ),
    # Firefox 136 on Windows
    BrowserProfile(
        name="Firefox 136 Windows",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:136.0) Gecko/20100101 Firefox/136.0",
        sec_ch_ua='"Firefox";v="136", "Not)A;Brand";v="99"',
        sec_ch_ua_platform='"Windows"',
        sec_ch_ua_mobile="?0",
    ),
    # Firefox 136 on macOS
    BrowserProfile(
        name="Firefox 136 macOS",
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:136.0) Gecko/20100101 Firefox/136.0",
        sec_ch_ua='"Firefox";v="136", "Not)A;Brand";v="99"',
        sec_ch_ua_platform='"macOS"',
        sec_ch_ua_mobile="?0",
    ),
    # Firefox 136 on Linux
    BrowserProfile(
        name="Firefox 136 Linux",
        user_agent="Mozilla/5.0 (X11; Linux x86_64; rv:136.0) Gecko/20100101 Firefox/136.0",
        sec_ch_ua='"Firefox";v="136", "Not)A;Brand";v="99"',
        sec_ch_ua_platform='"Linux"',
        sec_ch_ua_mobile="?0",
    ),
    # Safari 18.4 on macOS
    BrowserProfile(
        name="Safari 18.4 macOS",
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.4 Safari/605.1.15",
        sec_ch_ua='"Safari";v="18.4", "Apple Computer, Inc."',
        sec_ch_ua_platform='"macOS"',
        sec_ch_ua_mobile="?0",
    ),
    # Safari 18.4 on iOS
    BrowserProfile(
        name="Safari 18.4 iOS",
        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 18_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.4 Mobile/15E148 Safari/604.1",
        sec_ch_ua='"Safari";v="18.4", "Apple Computer, Inc."',
        sec_ch_ua_platform='"iOS"',
        sec_ch_ua_mobile="?1",
    ),
    # Opera 121 on Windows
    BrowserProfile(
        name="Opera 121 Windows",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36 OPR/121.0.0.0",
        sec_ch_ua='"Chromium";v="147", "Opera";v="121", "Not:A-Brand";v="99"',
        sec_ch_ua_platform='"Windows"',
        sec_ch_ua_mobile="?0",
    ),
    # Opera 121 on macOS
    BrowserProfile(
        name="Opera 121 macOS",
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36 OPR/121.0.0.0",
        sec_ch_ua='"Chromium";v="147", "Opera";v="121", "Not:A-Brand";v="99"',
        sec_ch_ua_platform='"macOS"',
        sec_ch_ua_mobile="?0",
    ),
    # Brave 1.78 on Windows
    BrowserProfile(
        name="Brave 1.78 Windows",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
        sec_ch_ua='"Chromium";v="147", "Brave";v="147", "Not:A-Brand";v="99"',
        sec_ch_ua_platform='"Windows"',
        sec_ch_ua_mobile="?0",
    ),
    # Brave 1.78 on macOS
    BrowserProfile(
        name="Brave 1.78 macOS",
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
        sec_ch_ua='"Chromium";v="147", "Brave";v="147", "Not:A-Brand";v="99"',
        sec_ch_ua_platform='"macOS"',
        sec_ch_ua_mobile="?0",
    ),
    # Vivaldi 7.3 on Windows
    BrowserProfile(
        name="Vivaldi 7.3 Windows",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36 Vivaldi/7.3.3635.3",
        sec_ch_ua='"Chromium";v="147", "Vivaldi";v="7.3", "Not:A-Brand";v="99"',
        sec_ch_ua_platform='"Windows"',
        sec_ch_ua_mobile="?0",
    ),
    # Chrome 147 on Android
    BrowserProfile(
        name="Chrome 147 Android",
        user_agent="Mozilla/5.0 (Linux; Android 15; Pixel 9 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Mobile Safari/537.36",
        sec_ch_ua='"Chromium";v="147", "Google Chrome";v="147", "Not:A-Brand";v="99"',
        sec_ch_ua_platform='"Android"',
        sec_ch_ua_mobile="?1",
    ),
    # Edge 147 on Android
    BrowserProfile(
        name="Edge 147 Android",
        user_agent="Mozilla/5.0 (Linux; Android 15; Pixel 9 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Mobile Safari/537.36 EdgA/147.0.0.0",
        sec_ch_ua='"Chromium";v="147", "Microsoft Edge";v="147", "Not:A-Brand";v="99"',
        sec_ch_ua_platform='"Android"',
        sec_ch_ua_mobile="?1",
    ),
    # Firefox 136 on Android
    BrowserProfile(
        name="Firefox 136 Android",
        user_agent="Mozilla/5.0 (Android 15; Mobile; rv:136.0) Gecko/136.0 Firefox/136.0",
        sec_ch_ua='"Firefox";v="136", "Not)A;Brand";v="99"',
        sec_ch_ua_platform='"Android"',
        sec_ch_ua_mobile="?1",
    ),
    # Safari on iPadOS
    BrowserProfile(
        name="Safari 18.4 iPadOS",
        user_agent="Mozilla/5.0 (iPad; CPU OS 18_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.4 Mobile/15E148 Safari/604.1",
        sec_ch_ua='"Safari";v="18.4", "Apple Computer, Inc."',
        sec_ch_ua_platform='"iPadOS"',
        sec_ch_ua_mobile="?1",
    ),
    # Chrome 146 on Windows (previous stable)
    BrowserProfile(
        name="Chrome 146 Windows",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        sec_ch_ua='"Chromium";v="146", "Google Chrome";v="146", "Not:A-Brand";v="99"',
        sec_ch_ua_platform='"Windows"',
        sec_ch_ua_mobile="?0",
    ),
]


class BrowserProfiles:
    """Manages browser profile selection and header injection.

    Ported from SearchWala src/config.rs: random_browser_headers()
    and apply_browser_headers().
    """

    def __init__(self, profiles: list[BrowserProfile] | None = None) -> None:
        self.profiles = profiles or PROFILES

    def get_random_profile(self) -> BrowserProfile:
        """Return a randomly selected browser profile."""
        return random.choice(self.profiles)

    def apply_to_headers(
        self, headers: dict[str, str], profile: BrowserProfile | None = None
    ) -> dict[str, str]:
        """Inject browser profile headers into a request headers dict.

        Modifies the dict in place and returns it.

        Args:
            headers: Existing headers dict to augment.
            profile: BrowserProfile to use. If None, picks randomly.

        Returns:
            The augmented headers dict.
        """
        if profile is None:
            profile = self.get_random_profile()

        headers["User-Agent"] = profile.user_agent
        headers["Accept"] = profile.accept
        headers["Accept-Language"] = profile.accept_language
        headers["Accept-Encoding"] = profile.accept_encoding
        headers["Sec-CH-UA"] = profile.sec_ch_ua

        # Conditionally add platform-specific headers
        if profile.sec_ch_ua_platform:
            headers["Sec-CH-UA-Platform"] = profile.sec_ch_ua_platform
        if profile.sec_ch_ua_mobile:
            headers["Sec-CH-UA-Mobile"] = profile.sec_ch_ua_mobile

        return headers
