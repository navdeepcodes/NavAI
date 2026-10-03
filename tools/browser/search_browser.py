"""Web search.

General web results first, news only as a fallback. An earlier version used a
news feed for everything, which meant a query like "open rocket" came back with
sports headlines instead of the rocketry software the user meant.
"""
from __future__ import annotations

import html
import re
import subprocess
from urllib.parse import quote, unquote

from logs.logger import logger

from tools.browser.open_url import open_url

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

MAX_RESULTS = 5

# (title, snippet, url) -- the url may be empty.
Result = tuple[str, str, str]


def _clean(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", "", fragment)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _fetch(url: str, timeout: int = 9, post: str | None = None) -> str:
    # Real web pages are UTF-8 and routinely carry non-ASCII punctuation
    # (curly quotes, em dashes). text=True alone decodes with the platform's
    # locale encoding — cp1252 on Windows — which raises on the first such
    # byte. Every real search would eventually hit one.
    command = [
        "curl", "-s", "-L", "--max-time", str(timeout), "-A", _USER_AGENT,
        "-H", "Accept-Language: en-US,en;q=0.9",
    ]
    if post is not None:
        command += ["-d", post]
    result = subprocess.run(
        [*command, url],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout + 3,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return result.stdout if result.returncode == 0 else ""


# ── Brave ────────────────────────────────────────────────────
#
# First choice: its results are relevant to the *meaning* of a long, specific
# query. Measured on the same query about F1 aerodynamics surrogate models,
# Bing matched the word "Deep" and returned DeepL, DeepSeek and DeepAI, while
# Brave returned the actual papers.

def _brave_results(query: str) -> list[Result]:
    page = _fetch(f"https://search.brave.com/search?q={quote(query)}&source=web")
    if not page:
        return []

    found: list[Result] = []
    for block in re.split(r'<div class="snippet[^"]*"\s+data-pos=', page)[1:]:
        link = re.search(r'<a href="(https?://[^"]+)"', block)
        title = re.search(r'class="title[^"]*"[^>]*>(.*?)</div>', block, re.S)
        if not link or not title:
            continue
        name = _clean(title.group(1))
        if not name:
            continue
        desc = re.search(
            r'class="(?:content|snippet-description)[^"]*"[^>]*>(.*?)</div>', block, re.S)
        snippet = _clean(desc.group(1)) if desc else ""
        found.append((name, snippet if snippet.lower() != "pdf" else "", html.unescape(link.group(1))))
        if len(found) >= MAX_RESULTS:
            break
    return found


# ── DuckDuckGo ───────────────────────────────────────────────
#
# A POST, like its own search form. A plain GET is answered with "bots use
# DuckDuckGo too" almost at once; the form post is let through for a while.

def _ddg_results(query: str) -> list[Result]:
    page = _fetch("https://html.duckduckgo.com/html/", post=f"q={quote(query)}")
    if not page or "result__a" not in page:
        return []

    found: list[Result] = []
    for block in page.split('class="result__a"')[1:]:
        link = re.search(r'href="([^"]+)"', block)
        title = re.search(r">(.*?)</a>", block, re.S)
        if not link or not title:
            continue
        name = _clean(title.group(1))
        url = link.group(1)
        wrapped = re.search(r"uddg=([^&]+)", url)
        if wrapped:
            url = unquote(wrapped.group(1))
        elif url.startswith("//"):
            url = "https:" + url
        snippet_match = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', block, re.S)
        snippet = _clean(snippet_match.group(1)) if snippet_match else ""
        if name:
            found.append((name, snippet, url))
        if len(found) >= MAX_RESULTS:
            break
    return found


# ── Bing (last resort) ───────────────────────────────────────

def _web_results(query: str) -> list[Result]:
    page = _fetch(f"https://www.bing.com/search?q={quote(query)}")
    if not page:
        return []

    found: list[Result] = []

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

        found.append((title, snippet, ""))
        if len(found) >= MAX_RESULTS:
            break

    return found


# ── News ─────────────────────────────────────────────────────

def _news_results(query: str) -> list[Result]:
    feed = _fetch(
        "https://news.google.com/rss/search?"
        f"q={quote(query)}&hl=en-US&gl=US&ceid=US:en"
    )
    if not feed:
        return []

    found: list[Result] = []

    for item in re.findall(r"<item>(.*?)</item>", feed, re.S)[:MAX_RESULTS]:
        title_match = re.search(r"<title>(.*?)</title>", item, re.S)
        if not title_match:
            continue
        title = _clean(title_match.group(1))
        if title:
            found.append((title, "", ""))

    return found


# ── Public ───────────────────────────────────────────────────

def search_browser(query: str) -> str:
    if not query:
        raise ValueError("Search query is required.")

    logger.info("Web search: %s", query)

    # Engines are tried in order of how well they answer, and each one is
    # allowed to fail on its own: they rate-limit and change their markup, so
    # relying on a single one means "search doesn't work" every time it does.
    engines = (
        ("Brave", _brave_results, "Search results"),
        ("DuckDuckGo", _ddg_results, "Search results"),
        ("Bing", _web_results, "Search results"),
        # Some queries are genuinely news-shaped, and the feed still
        # answers those when the general indexes give nothing.
        ("Google News", _news_results, "Recent news"),
    )
    for name, engine, source in engines:
        try:
            results = engine(query)
        except Exception as exc:
            logger.warning("Web search via %s failed: %s", name, exc)
            continue
        if not results:
            logger.info("Web search via %s returned nothing; trying the next.", name)
            continue

        logger.info("Web search via %s: %d results", name, len(results))
        lines = []
        for index, (title, snippet, url) in enumerate(results, start=1):
            entry = f"{index}. {title}"
            if snippet:
                # Enough to judge relevance; the context window is not free.
                entry += f"\n   {snippet[:300].rstrip()}{'…' if len(snippet) > 300 else ''}"
            if url:
                entry += f"\n   {url}"
            lines.append(entry)
        return f"{source}:\n\n" + "\n\n".join(lines)

    open_url(f"https://www.google.com/search?q={quote(query)}")
    return (
        f"I opened a search for '{query}' in your browser, but couldn't read "
        "the results directly."
    )
