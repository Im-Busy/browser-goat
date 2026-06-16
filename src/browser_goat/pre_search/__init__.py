"""Pre-search layer: query intelligence, language detection, browser profile rotation."""

from browser_goat.pre_search.browser_profiles import PROFILES, BrowserProfiles
from browser_goat.pre_search.language_detect import (
    detect_language_params,
    get_search_engines_for_language,
)
from browser_goat.pre_search.query_intel import QueryIntel

__all__ = [
    "QueryIntel",
    "BrowserProfiles",
    "PROFILES",
    "detect_language_params",
    "get_search_engines_for_language",
]
