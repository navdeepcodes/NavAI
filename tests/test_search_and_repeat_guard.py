"""Two failures found in a real Mike log, pinned so they can't come back.

1. A tool that errored instantly was retried with identical arguments until the
   step limit -- twenty times -- and the user got a wall of failed steps and no
   answer. The runtime now refuses to repeat a call that has failed twice in a
   row, and tells the model to explain instead.

2. Web search returned results, but for a long specific query Bing matched the
   word "Deep" and returned DeepL, DeepSeek and DeepAI. Search now tries
   several engines in turn, so one blocking or answering badly isn't the end.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401


# ── the repeat guard ──────────────────────────────────────────

def _runtime(outcomes):
    """A CoreRuntime whose tools do whatever `outcomes(name, args)` says."""
    from brain.core_runtime import CoreRuntime

    rt = CoreRuntime()
    calls = []

    def fake(name, args):
        calls.append((name, dict(args)))
        return outcomes(name, args)

    rt._dispatch_tool = fake
    return rt, calls


_FAIL = {"status": "error", "error": "Unknown tool: browser"}
_OK = {"status": "success", "result": "fine"}


def test_the_same_failing_call_is_not_repeated_twenty_times():
    rt, calls = _runtime(lambda n, a: _FAIL)
    args = {"query": "surrogate modelling"}

    results = [rt._execute_tool("search_web", args) for _ in range(20)]

    assert len(calls) == rt.MAX_IDENTICAL_FAILURES, "the tool must stop being run"
    assert results[0]["status"] == results[1]["status"] == "error"
    refused = results[-1]
    assert refused["status"] == "error" and refused["retry_safe"] is False
    assert "not run again" in refused["error"]
    assert "Tell the user" in refused["note"], "the model must be told to explain"


def test_a_different_call_in_between_resets_the_count():
    """Run the tests, fix the code, run them again is ordinary work."""
    state = {"fixed": False}

    def outcomes(name, args):
        if name == "edit_file":
            state["fixed"] = True
            return _OK
        return _OK if state["fixed"] else _FAIL

    rt, calls = _runtime(outcomes)
    run = {"command": "pytest"}
    rt._execute_tool("run_command", run)
    rt._execute_tool("run_command", run)
    rt._execute_tool("edit_file", {"path": "a.py"})
    result = rt._execute_tool("run_command", run)

    assert result["status"] == "success"
    assert len(calls) == 4, "nothing was refused"


def test_different_arguments_are_a_different_call():
    rt, calls = _runtime(lambda n, a: _FAIL)
    for q in ("one", "two", "three", "four"):
        rt._execute_tool("search_web", {"query": q})
    assert len(calls) == 4


def test_a_new_message_starts_fresh():
    rt, calls = _runtime(lambda n, a: _FAIL)
    for _ in range(5):
        rt._execute_tool("search_web", {"query": "x"})
    assert len(calls) == rt.MAX_IDENTICAL_FAILURES

    rt._record_user_turn("try again")
    rt._execute_tool("search_web", {"query": "x"})
    assert len(calls) == rt.MAX_IDENTICAL_FAILURES + 1


# ── web search ────────────────────────────────────────────────

_BRAVE = (
    '<div class="snippet svelte-x" data-pos="1"><a href="https://example.org/paper">'
    '<div class="title svelte-y">A relevant paper</div></a>'
    '<div class="content svelte-z">What the paper is about.</div></div>'
)
_DDG = (
    '<a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg='
    'https%3A%2F%2Fexample.com%2Fpage&rut=abc">Found on DuckDuckGo</a>'
    '<a class="result__snippet" href="x">A snippet.</a>'
)
_BING = (
    '<li class="b_algo"><h2><a href="https://b.example">Bing title</a></h2>'
    '<p>Bing snippet</p></li>'
)


def _patch(monkeypatch, pages: dict):
    from tools.browser import search_browser as sb

    def fake_fetch(url, timeout=9, post=None):
        for marker, body in pages.items():
            if marker in url:
                return body
        return ""

    monkeypatch.setattr(sb, "_fetch", fake_fetch)
    opened = []
    monkeypatch.setattr(sb, "open_url", lambda u: opened.append(u))
    return sb, opened


def test_search_uses_the_first_engine_that_answers(monkeypatch):
    sb, opened = _patch(monkeypatch, {"brave.com": _BRAVE, "bing.com": _BING})
    out = sb.search_browser("anything")
    assert "A relevant paper" in out and "https://example.org/paper" in out
    assert "Bing title" not in out and not opened


def test_search_falls_through_when_an_engine_is_blocked(monkeypatch):
    sb, opened = _patch(monkeypatch, {"duckduckgo.com": _DDG, "bing.com": _BING})
    out = sb.search_browser("anything")            # Brave returns nothing
    assert "Found on DuckDuckGo" in out
    assert "https://example.com/page" in out, "the DuckDuckGo redirect is unwrapped"
    assert not opened


def test_search_survives_an_engine_that_raises(monkeypatch):
    sb, _ = _patch(monkeypatch, {"bing.com": _BING})
    monkeypatch.setattr(sb, "_brave_results", lambda q: (_ for _ in ()).throw(RuntimeError("boom")))
    assert "Bing title" in sb.search_browser("anything")


def test_search_opens_the_browser_only_when_every_engine_fails(monkeypatch):
    sb, opened = _patch(monkeypatch, {})
    out = sb.search_browser("anything")
    assert "opened a search" in out and len(opened) == 1


def test_long_snippets_are_trimmed_to_spare_the_context(monkeypatch):
    long_body = _BRAVE.replace("What the paper is about.", "word " * 200)
    sb, _ = _patch(monkeypatch, {"brave.com": long_body})
    out = sb.search_browser("anything")
    assert "…" in out and len(out) < 700
