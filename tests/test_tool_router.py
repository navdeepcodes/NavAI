"""The tool router must never leave Mike unable to do what was asked.

Offering fewer tools makes the local model several times faster per step, but
a tool that is not offered cannot be used. So the important tests are the
ones where a request NEEDS a specialist tool: those must always get it. The
saving is tested too, because a router that never narrows is just noise.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401

from brain import permissions, tool_router
from brain.core_tools import OLLAMA_TOOLS


def _names(tools):
    return [t["function"]["name"] for t in tools]


def _offered(*user_messages, used=()):
    history = []
    for text in user_messages:
        history.append({"role": "user", "content": text})
    if used:
        history.append({"role": "assistant", "content": "",
                        "tool_calls": [{"function": {"name": n, "arguments": {}}} for n in used]})
    return _names(tool_router.route(permissions.allowed_tools(OLLAMA_TOOLS), history))


# ── a request that needs a specialist tool always gets it ─────

@pytest.mark.parametrize("request_text, must_have", [
    ("make a presentation about photosynthesis", "create_presentation"),
    ("Summarise this PDF for me", "search_document"),
    ("read /Users/me/Downloads/syllabus.pdf", "document_info"),
    ("write my lab report in APA with a title page", "create_document"),
    ("turn this into a Word document", "create_document"),
    ("save it as a Microsoft Word file", "create_document"),
    ("add a column for total marks in my spreadsheet", "edit_spreadsheet"),
    ("open budget.xlsx and sum the rows", "read_spreadsheet"),
    ("email my professor that I'll be late", "send_email"),
    ("click the submit button", "click_element"),
    ("what's on my screen right now?", "see_screen"),
    ("scroll down and press enter", "scroll_ui"),
])
def test_a_request_that_needs_a_specialist_tool_gets_it(request_text, must_have):
    assert must_have in _offered(request_text), request_text


def test_a_follow_up_keeps_what_the_last_request_needed():
    """'yes, do it' says nothing about documents, but the turn before did."""
    offered = _offered("make a presentation on the solar system", "yes go ahead")
    assert "create_presentation" in offered


def test_a_group_already_used_in_the_conversation_stays_offered():
    offered = _offered("hmm", "ok", "right", "and now?", used=("create_document",))
    assert "create_document" in offered and "pdf_edit" in offered


# ── ordinary requests get a lighter prompt ────────────────────

@pytest.mark.parametrize("request_text", [
    "What is the capital of France?",
    "Search the web for the latest Python release",
    "Create a file called hello.txt containing hello",
    "Remember that my exam is on Friday",
    "How many days are there until Diwali?",
    # Found in a real run: "word" is just a word, not Microsoft Word.
    "Create a file at /tmp/x/hello.txt containing exactly the word hello.",
    "What does the word serendipity mean?",
])
def test_an_ordinary_request_is_not_burdened_with_specialist_tools(request_text):
    full = _names(permissions.allowed_tools(OLLAMA_TOOLS))
    offered = _offered(request_text)
    assert len(offered) < len(full), "nothing was saved"
    for everyday in ("search_web", "read_file", "write_file", "run_command",
                     "open_application", "remember", "think", "calculate"):
        assert everyday in offered, f"{everyday} must always be offered"


def test_the_saving_is_worth_having():
    tools = permissions.allowed_tools(OLLAMA_TOOLS)
    history = [{"role": "user", "content": "What is the capital of France?"}]
    full = len(json.dumps(tools))
    routed = len(json.dumps(tool_router.route(tools, history)))
    assert routed < full * 0.75, f"only {1 - routed / full:.0%} saved"


# ── mechanics ─────────────────────────────────────────────────

def test_order_is_preserved():
    tools = permissions.allowed_tools(OLLAMA_TOOLS)
    routed = _names(tool_router.route(tools, [{"role": "user", "content": "hi"}]))
    original = [n for n in _names(tools) if n in routed]
    assert routed == original


def test_it_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("MIKE_ROUTE_TOOLS", "0")
    tools = permissions.allowed_tools(OLLAMA_TOOLS)
    assert tool_router.route(tools, [{"role": "user", "content": "hi"}]) == tools


def test_multimodal_message_content_does_not_crash_it():
    history = [{"role": "user", "content": [{"type": "text", "text": "make slides"}]}]
    assert "create_presentation" in _names(
        tool_router.route(permissions.allowed_tools(OLLAMA_TOOLS), history))


# ── the runtime uses it for the local model only ──────────────

def test_the_local_model_is_routed_and_the_cloud_is_not():
    from brain.core_runtime import CoreRuntime

    rt = CoreRuntime()
    rt._core.history.append({"role": "user", "content": "What is the capital of France?"})
    full = permissions.allowed_tools(OLLAMA_TOOLS)

    class _Cloud:
        def _use_cloud(self):
            return True

    class _Local:
        def _use_cloud(self):
            return False

    rt._brain = _Cloud()
    assert len(rt._offered_tools()) == len(full), "Fast mode keeps every tool"
    rt._brain = _Local()
    assert len(rt._offered_tools()) < len(full), "the local model gets the lighter set"


def test_a_routing_failure_falls_back_to_every_tool(monkeypatch):
    from brain.core_runtime import CoreRuntime

    rt = CoreRuntime()
    monkeypatch.setattr(tool_router, "route", lambda *_a: (_ for _ in ()).throw(RuntimeError("x")))
    assert rt._offered_tools() == permissions.allowed_tools(OLLAMA_TOOLS)
