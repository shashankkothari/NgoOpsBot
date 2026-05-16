"""Web search tool for agent use.

Uses DuckDuckGo's free instant-answer JSON API (no API key required) plus
a lightweight HTML scrape fallback for broader result coverage.

Primary use cases for NGO agents:
- Current regulatory information (FCRA rules, TDS rates, compliance deadlines)
- Grant opportunities and funder information
- NGO sector benchmarks and best practices
- News about donors or sector trends

Note: DuckDuckGo's instant-answer API is best for well-known topics and
regulatory queries. For narrow/niche queries the HTML fallback is used.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx

from app.core.logging import get_logger

log = get_logger(__name__)

# User-agent to identify ourselves (DuckDuckGo allows this)
_USER_AGENT = "NGO-OpsBot/1.0 (+https://github.com/ngoopsbot)"

# Timeouts for web requests
_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

# DuckDuckGo endpoints
_DDG_API_URL = "https://api.duckduckgo.com/"
_DDG_LITE_URL = "https://lite.duckduckgo.com/lite/"


async def web_search(query: str, max_results: int = 5) -> str:
    """Search the web and return a formatted string of results.

    Tries DuckDuckGo's instant answer API first (structured JSON); falls back
    to the DDG Lite HTML endpoint for broader coverage.

    Args:
        query: Search query string.
        max_results: Maximum number of results to include (default 5).

    Returns:
        Formatted string with search results, suitable for inclusion in
        a Claude conversation. Each result includes a title, URL, and snippet.
    """
    max_results = max(1, min(max_results, 20))

    try:
        result = await _search_ddg_api(query, max_results)
        if result and result != "No results found.":
            log.info("web_search_ddg_api", query_length=len(query), result_length=len(result))
            return result
    except Exception as exc:
        log.warning("web_search_ddg_api_failed", error=str(exc))

    # Fallback to HTML scrape
    try:
        result = await _search_ddg_lite(query, max_results)
        log.info("web_search_ddg_lite", query_length=len(query), result_length=len(result))
        return result
    except Exception as exc:
        log.error("web_search_ddg_lite_failed", error=str(exc))
        return f"Web search is currently unavailable. Error: {exc}"


async def _search_ddg_api(query: str, max_results: int) -> str:
    """DuckDuckGo instant answer API — returns structured knowledge card data."""
    params = {
        "q": query,
        "format": "json",
        "no_html": "1",
        "skip_disambig": "1",
        "no_redirect": "1",
    }

    async with httpx.AsyncClient(
        headers={"User-Agent": _USER_AGENT},
        timeout=_TIMEOUT,
    ) as client:
        resp = await client.get(_DDG_API_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    parts: list[str] = []

    # Abstract (knowledge card — usually Wikipedia or authoritative source)
    abstract = data.get("Abstract", "").strip()
    abstract_url = data.get("AbstractURL", "")
    if abstract:
        parts.append(f"**Summary**\n{abstract}")
        if abstract_url:
            parts[-1] += f"\nSource: {abstract_url}"

    # Answer (instant answer, e.g. calculations or factual one-liners)
    answer = data.get("Answer", "").strip()
    if answer and answer != abstract:
        parts.append(f"**Answer**\n{answer}")

    # Related topics — rich snippet results
    related = data.get("RelatedTopics", [])
    count = 0
    for item in related:
        if count >= max_results:
            break
        # Items can be either a topic dict or a category with nested Topics
        if isinstance(item, dict):
            text = item.get("Text", "").strip()
            url = item.get("FirstURL", "")
            if text:
                parts.append(f"• {text}" + (f"\n  {url}" if url else ""))
                count += 1
        elif isinstance(item, dict) and "Topics" in item:
            for sub in item.get("Topics", []):
                if count >= max_results:
                    break
                text = sub.get("Text", "").strip()
                url = sub.get("FirstURL", "")
                if text:
                    parts.append(f"• {text}" + (f"\n  {url}" if url else ""))
                    count += 1

    if not parts:
        return ""

    return f"**Web Search Results for: {query}**\n\n" + "\n\n".join(parts)


async def _search_ddg_lite(query: str, max_results: int) -> str:
    """Scrape DuckDuckGo Lite HTML for broader search coverage.

    DDG Lite is a minimal HTML version of DuckDuckGo — no JavaScript,
    no tracking — making it easy to parse for snippets and URLs.
    """
    async with httpx.AsyncClient(
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "text/html",
        },
        timeout=_TIMEOUT,
        follow_redirects=True,
    ) as client:
        resp = await client.post(_DDG_LITE_URL, data={"q": query, "o": "json"})
        resp.raise_for_status()
        html = resp.text

    results = _parse_ddg_lite_html(html, max_results)

    if not results:
        return f"No web results found for: {query}"

    lines = [f"**Web Search Results for: {query}**\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. **{r['title']}**")
        if r.get("url"):
            lines.append(f"   {r['url']}")
        if r.get("snippet"):
            lines.append(f"   {r['snippet']}")
    return "\n".join(lines)


def _parse_ddg_lite_html(html: str, max_results: int) -> list[dict[str, str]]:
    """Extract result titles, URLs, and snippets from DDG Lite HTML.

    The HTML structure is simple enough to parse with regex — avoids the
    BS4 dependency which isn't in our pyproject.toml.
    """
    results: list[dict[str, str]] = []

    # Results are in <a class="result-link"> ... <a/> (title + URL)
    # and <td class="result-snippet"> (snippet)
    # Pattern: grab href and link text from result links
    link_pattern = re.compile(
        r'<a[^>]+class="result-link"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        re.DOTALL | re.IGNORECASE,
    )
    snippet_pattern = re.compile(
        r'class="result-snippet"[^>]*>\s*(.*?)\s*</td>',
        re.DOTALL | re.IGNORECASE,
    )

    links = link_pattern.findall(html)
    snippets = [m for m in snippet_pattern.findall(html)]

    for i, (url, title_html) in enumerate(links[:max_results]):
        title = re.sub(r"<[^>]+>", "", title_html).strip()
        snippet = ""
        if i < len(snippets):
            snippet = re.sub(r"<[^>]+>", " ", snippets[i]).strip()
            snippet = re.sub(r"\s+", " ", snippet)

        if title or url:
            results.append({
                "title": title or url,
                "url": _clean_ddg_url(url),
                "snippet": snippet,
            })

    return results


def _clean_ddg_url(url: str) -> str:
    """Extract the actual destination URL from DuckDuckGo's redirect wrapper."""
    # DDG Lite URLs look like: //duckduckgo.com/l/?uddg=https%3A%2F%2F...
    match = re.search(r"uddg=([^&]+)", url)
    if match:
        import urllib.parse
        return urllib.parse.unquote(match.group(1))
    # Direct URL (no redirect)
    if url.startswith("http"):
        return url
    return f"https:{url}" if url.startswith("//") else url
