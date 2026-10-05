import logging
import urllib.parse
import urllib.robotparser
from typing import Any

logger = logging.getLogger(__name__)

# Cache of robots.txt parsers per domain to avoid repeatedly fetching robots.txt
_ROBOTS_CACHE: dict[str, urllib.robotparser.RobotFileParser] = {}


def is_allowed_by_robots(url: str, user_agent: str = "*") -> bool:
    """
    Checks if fetching url is permitted by the domain's robots.txt.
    Fails open (allows) if robots.txt cannot be fetched or parsed.
    """
    try:
        parsed = urllib.parse.urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return True
        domain_root = f"{parsed.scheme}://{parsed.netloc}"
        if domain_root not in _ROBOTS_CACHE:
            rp = urllib.robotparser.RobotFileParser()
            robots_url = urllib.parse.urljoin(domain_root, "/robots.txt")
            rp.set_url(robots_url)
            try:
                rp.read()
            except Exception as e:
                logger.debug("Could not read robots.txt for %s: %s", domain_root, e)
            _ROBOTS_CACHE[domain_root] = rp
        return _ROBOTS_CACHE[domain_root].can_fetch(user_agent, url)
    except Exception as exc:
        logger.debug("Error checking robots.txt for %s: %s", url, exc)
        return True


def clean_extracted_text(raw_texts: list[str]) -> str:
    """Cleans and joins list of text snippets into readable article text."""
    cleaned_tokens = []
    for token in raw_texts:
        t = token.strip()
        if t:
            cleaned_tokens.append(t)
    return " ".join(cleaned_tokens)


def fetch_url_content(
    url: str,
    obey_robots: bool = True,
    max_chars: int = 6000,
) -> tuple[bool, str, dict[str, Any]]:
    """
    Fetches real page content using Scrapling.
    Attempts plain HTTP Fetcher first; falls back to StealthyFetcher if blocked (e.g. 403, 429, cloudflare).
    Respects robots.txt if obey_robots is True.

    Returns:
        (success: bool, content: str, metadata: dict)
    """
    if not url or not url.startswith(("http://", "https://")):
        return False, "", {"error": "Invalid or missing URL", "method": "none"}

    if obey_robots and not is_allowed_by_robots(url):
        logger.warning("Scrapling content fetch skipped: disallowed by robots.txt for %s", url)
        return False, "", {"error": "Disallowed by robots.txt", "method": "robots_txt_disallowed"}

    # 1. Try Scrapling plain HTTP Fetcher
    try:
        from scrapling.fetchers import Fetcher
        fetcher = Fetcher()
        resp = fetcher.get(url, timeout=15)
        if resp.status == 200:
            # Extract main article or body text
            texts = resp.css("article ::text").getall()
            if not texts:
                texts = resp.css("main ::text").getall()
            if not texts:
                texts = resp.css("body ::text").getall()

            cleaned = clean_extracted_text(texts)
            if cleaned and len(cleaned) > 100:
                truncated = cleaned[:max_chars]
                return True, truncated, {
                    "method": "plain_fetcher",
                    "status_code": resp.status,
                    "extracted_length": len(truncated),
                    "original_length": len(cleaned),
                }
        logger.info(
            "Plain Scrapling fetch returned status %s for %s, trying StealthyFetcher...",
            getattr(resp, "status", "unknown"),
            url,
        )
    except Exception as plain_err:
        logger.info("Plain Scrapling fetch failed for %s (%s), trying StealthyFetcher...", url, plain_err)

    # 2. Try StealthyFetcher as fallback if plain HTTP was blocked or yielded empty content
    try:
        from scrapling.fetchers import StealthyFetcher
        stealth = StealthyFetcher()
        resp = stealth.get(url, timeout=25)
        if getattr(resp, "status", None) == 200 or resp:
            texts = resp.css("article ::text").getall()
            if not texts:
                texts = resp.css("main ::text").getall()
            if not texts:
                texts = resp.css("body ::text").getall()

            cleaned = clean_extracted_text(texts)
            if cleaned and len(cleaned) > 100:
                truncated = cleaned[:max_chars]
                return True, truncated, {
                    "method": "stealthy_fetcher",
                    "status_code": getattr(resp, "status", 200),
                    "extracted_length": len(truncated),
                    "original_length": len(cleaned),
                }
    except Exception as stealth_err:
        logger.warning("StealthyFetcher failed for %s: %s", url, stealth_err)

    return False, "", {"error": "All Scrapling fetchers failed or returned empty content", "method": "failed"}
