"""Web search.

General web results first, news only as a fallback. An earlier version used a
news feed for everything, which meant a query like "open rocket" came back with
sports headlines instead of the rocketry software the user meant.
"""
from __future__ import annotations

import html
import re
import subprocess
from urllib.parse import quote

from logs.logger import logger

from tools.browser.open_url import open_url

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.0 Safari/605.1.15"
)

MAX_RESULTS = 5


def _clean(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", "", fragment)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _fetch(url: str, timeout: int = 9) -> str:
    result = subprocess.run(
        ["curl", "-s", "-L", "--max-time", str(timeout), "-A", _USER_AGENT, url],
        capture_output=True,
        text=True,
        timeout=timeout + 3,
    )
    return result.stdout if result.returncode == 0 else ""


# ── General web ──────────────────────────────────────────────

def _web_results(query: str) -> list[tuple[str, str]]:
    page = _fetch(f"https://www.bing.com/search?q={quote(query)}")
    if not page:
        return []

    found: list[tuple[str, str]] = []

    # Each organic result opens with this marker; splitting on it is steadier
    # than trying to match the closing tag across nested markup.
    for block in page.split('<li class="b_algo"')[1:]:
        title_match = re.search(r"<h2[^>]*>\s*<a[^>]*>(.*?)</a>", block, re.S)
        if not title_match:
            continue

        title = _clean(title_match.group(1))
        if not title:
            continue

        snippet_match = (
            re.search(r'<p class="b_lineclamp[^"]*"[^>]*>(.*?)</p>', block, re.S)
            or re.search(r"<p[^>]*>(.*?)</p>", block, re.S)
        )
        snippet = _clean(snippet_match.group(1)) if snippet_match else ""

        found.append((title, snippet))
        if len(found) >= MAX_RESULTS:
            break

    return found


# ── News ─────────────────────────────────────────────────────

def _news_results(query: str) -> list[tuple[str, str]]:
    feed = _fetch(
        "https://news.google.com/rss/search?"
        f"q={quote(query)}&hl=en-US&gl=US&ceid=US:en"
    )
    if not feed:
        return []

    found: list[tuple[str, str]] = []

    for item in re.findall(r"<item>(.*?)</item>", feed, re.S)[:MAX_RESULTS]:
        title_match = re.search(r"<title>(.*?)</title>", item, re.S)
        if not title_match:
            continue
        title = _clean(title_match.group(1))
        if title:
            found.append((title, ""))

    return found


# ── Public ───────────────────────────────────────────────────

def search_browser(query: str) -> str:
    if not query:
        raise ValueError("Search query is required.")

    logger.info("Web search: %s", query)

    try:
        results = _web_results(query)
        source = "Search results"

        if not results:
            # Some queries are genuinely news-shaped, and the feed still
            # answers those when the general index gives nothing.
            results = _news_results(query)
            source = "Recent news"

        if results:
            lines = []
            for index, (title, snippet) in enumerate(results, start=1):
                entry = f"{index}. {title}"
                if snippet:
                    entry += f"\n   {snippet}"
                lines.append(entry)

            return f"{source}:\n\n" + "\n\n".join(lines)

    except Exception as exc:
        logger.warning("Web search failed: %s", exc)

    open_url(f"https://www.google.com/search?q={quote(query)}")
    return (
        f"I opened a search for '{query}' in your browser, but couldn't read "
        "the results directly."
    )
