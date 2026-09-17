"""Conservative shared acceptance gate for successful page-fetch responses."""

from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

from browser_goat.models import FetchResult

_CHALLENGE_TITLES = {
    "just a moment", "checking your browser", "attention required | cloudflare",
    "security check", "verify you are human", "captcha", "access denied",
    "pardon our interruption", "are you a robot",
}
_PROMPT = re.compile(
    r"(?:please )?(?:verify|confirm) (?:that )?you(?:'re| are) (?:a )?human"
    r"|checking your browser|enable javascript(?: and cookies)?"
    r"|complete the (?:security check|captcha)",
    re.IGNORECASE,
)
_SHORT_PROMPT = re.compile(
    r"^(?:(?:you need to |please )?enable javascript(?: and cookies)?"
    r"(?: to (?:continue|run this app|view (?:this|the) (?:page|website)))?"
    r"|(?:please )?(?:verify|confirm) (?:that )?you(?:'re| are) (?:a )?human"
    r"|checking your browser)[.! ]*$",
    re.IGNORECASE,
)


def accept_response(result: FetchResult) -> FetchResult:
    """Reject empty/known interstitial responses without blacklisting topic words.

    Challenge vocabulary alone is insufficient: inspect titles, active challenge
    markup, and short prompt-only bodies, excluding code samples. This is a
    heuristic, not a general bot-wall detector or a guarantee of page relevance.
    """
    if not result.success:
        return result
    error = _rejection_reason(result.status_code, result.html)
    if error:
        return result.model_copy(update={"success": False, "error": error})
    return result


def _rejection_reason(status: int, html: str) -> str | None:
    if not 200 <= status < 300:
        return f"HTTP {status} is not a successful page response"
    if not html.strip():
        return "Empty page response"
    soup = BeautifulSoup(html, "lxml")
    structured_content = _has_structured_content(soup)
    title = re.sub(r"[.!?]+", "", soup.title.get_text(" ", strip=True).lower()).strip() if soup.title else ""
    # Documentation often contains verbatim challenge markup and instructions.
    for node in soup.select("pre, code, samp, template"):
        node.decompose()
    challenge_markup = soup.select_one(
        "#challenge-form, #cf-challenge-running, #cf-chl-widget, "
        ".cf-turnstile, .g-recaptcha, .h-captcha, "
        "iframe[src*='challenges.cloudflare.com'], iframe[src*='/recaptcha/']"
    ) is not None
    challenge_script = any(
        "/cdn-cgi/challenge-platform/" in str(node.get("src", ""))
        or "_cf_chl_opt" in node.get_text()
        for node in soup.find_all("script")
    )
    for node in soup.select("script, style, title, meta, link, base"):
        node.decompose()
    text = soup.get_text(" ", strip=True)
    if title in _CHALLENGE_TITLES and (
        title in {"just a moment", "checking your browser", "attention required | cloudflare"}
        or challenge_markup or challenge_script or (len(text) < 2000 and _PROMPT.search(text))
    ):
        return "Recognized challenge/interstitial page"
    if (challenge_markup or challenge_script) and (not text or (len(text) < 2000 and _PROMPT.search(text))):
        return "Recognized challenge/interstitial page"
    # A noscript warning on a complete document is harmless; one that is the
    # only body text indicates an unrendered JS shell and should escalate.
    for node in soup.select("noscript"):
        node.decompose()
    visible = soup.get_text(" ", strip=True)
    if not visible:
        # Code-only documents remain useful, even though excluded from detection.
        original = BeautifulSoup(html, "lxml")
        for node in original.select("script, style, title, meta, link, base, noscript"):
            node.decompose()
        if not original.get_text(" ", strip=True) and not structured_content:
            return "Empty or JavaScript-only page response"
    if len(visible) < 200 and _SHORT_PROMPT.fullmatch(visible) and soup.select_one("article, main") is None:
        return "Recognized challenge/interstitial prompt"
    return None


def _has_structured_content(soup: BeautifulSoup) -> bool:
    """Preserve pages supported by the extractor's JSON-LD/meta fallback tiers."""
    for node in soup.select('meta[name="description"], meta[property="og:description"]'):
        if len(str(node.get("content", "")).strip()) >= 50:
            return True
    for node in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(node.string or "")
        except (ValueError, TypeError):
            continue
        items = data.get("@graph", [data]) if isinstance(data, dict) else []
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and any(
                isinstance(item.get(key), str) and len(item[key].strip()) >= 50
                for key in ("articleBody", "description")
            ):
                return True
    return False
