"""
Web search for SHAIL — augments local Gemma with live internet results.

Uses DuckDuckGo HTML scraping (no API key, no rate limits, free).
Falls back gracefully to no-search if the network is unavailable.

Public:
  needs_web_search(query) -> bool        — fast heuristic, no LLM call
  search(query, max=3, timeout=3)        — returns [{title, url, snippet}]

Latency budget: 3 s hard timeout. Cache hits are sub-millisecond.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
import time
from typing import List, Dict
from urllib.parse import quote_plus, unquote, urlparse, parse_qs

import httpx

logger = logging.getLogger(__name__)

# ── Heuristic classifier (no LLM call, ~0 ms) ───────────────────────────────

_TIME_TRIGGERS = {
    "today", "tomorrow", "yesterday", "tonight", "now", "latest", "current",
    "recent", "this week", "this month", "this year", "right now",
    "breaking", "news", "update", "updated", "live",
}

_FACT_TRIGGERS = {
    "who is", "who won", "who's", "what is", "what's the price", "price of",
    "stock", "weather", "score", "result", "schedule", "release date",
    "when does", "when is", "when will", "where is", "how much",
}

_NEVER_TRIGGERS = {  # purely conversational — never search
    "how are you", "thanks", "thank you", "hello", "hi ", "hey ",
    "translate", "summarize the file", "explain my code",
}


def needs_web_search(query: str) -> bool:
    """True if the query likely needs current internet info."""
    q = query.lower().strip()
    if len(q) < 4:
        return False
    if any(t in q for t in _NEVER_TRIGGERS):
        return False
    if any(t in q for t in _TIME_TRIGGERS):
        return True
    if any(t in q for t in _FACT_TRIGGERS):
        return True
    # Year mentions (2024/2025/2026) => probably wants current info
    if re.search(r"\b20\d{2}\b", q):
        return True
    return False


# ── Result cache (TTL = 30 min) ─────────────────────────────────────────────

_CACHE: Dict[str, tuple[float, list]] = {}
_CACHE_TTL = 1800.0  # 30 min
_CACHE_MAX = 256


def _cache_get(query: str) -> list | None:
    item = _CACHE.get(query)
    if not item:
        return None
    ts, results = item
    if time.time() - ts > _CACHE_TTL:
        _CACHE.pop(query, None)
        return None
    return results


def _cache_set(query: str, results: list) -> None:
    if len(_CACHE) >= _CACHE_MAX:
        # Drop oldest
        oldest = min(_CACHE.items(), key=lambda kv: kv[1][0])[0]
        _CACHE.pop(oldest, None)
    _CACHE[query] = (time.time(), results)


# ── DuckDuckGo HTML search (no API key) ─────────────────────────────────────

_DDG_URL = "https://html.duckduckgo.com/html/"
_RESULT_RE = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?'
    r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
    re.S,
)
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_tags(s: str) -> str:
    return html.unescape(_TAG_RE.sub("", s)).strip()


def _resolve_ddg_url(href: str) -> str:
    """DuckDuckGo wraps result URLs as /l/?uddg=<encoded>. Unwrap it."""
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        qs = parse_qs(parsed.query)
        target = qs.get("uddg", [""])[0]
        if target:
            return unquote(target)
    return href


async def _search_ddg(query: str, max_results: int, timeout: float) -> list:
    """Single-shot HTML scrape of DuckDuckGo. Returns up to max_results dicts."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
                      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    }
    params = {"q": query}
    async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
        resp = await client.post(_DDG_URL, data=params)
        resp.raise_for_status()
        html = resp.text

    results = []
    for match in _RESULT_RE.finditer(html):
        url     = _resolve_ddg_url(match.group(1))
        title   = _strip_tags(match.group(2))[:120]
        snippet = _strip_tags(match.group(3))[:280]
        if not url or not title:
            continue
        results.append({"title": title, "url": url, "snippet": snippet})
        if len(results) >= max_results:
            break
    return results


async def search(query: str, max_results: int = 3, timeout: float = 3.0) -> list:
    """
    Public entrypoint. Returns up to `max_results` snippets, or [] on failure.
    Never raises — failures are logged and treated as "no results".
    """
    cached = _cache_get(query)
    if cached is not None:
        return cached

    try:
        results = await asyncio.wait_for(
            _search_ddg(query, max_results, timeout), timeout=timeout
        )
        _cache_set(query, results)
        return results
    except asyncio.TimeoutError:
        logger.warning("web_search timeout (%.1fs) for: %s", timeout, query)
    except Exception as e:
        logger.warning("web_search failed for %r: %s", query, e)
    return []


def format_for_prompt(results: list) -> str:
    """Format search results as numbered context block for injection into Gemma prompt."""
    if not results:
        return ""
    lines = ["[Web search results - fetched live]"]
    for i, r in enumerate(results, 1):
        lines.append(f"[{i}] {r['title']}")
        lines.append(f"    URL: {r['url']}")
        lines.append(f"    {r['snippet']}")
    lines.append("\nUse the above sources if relevant. Cite them inline as [1], [2], etc. "
                 "If they're not relevant, ignore them.")
    return "\n".join(lines)
