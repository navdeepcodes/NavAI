"""Offer the local model only the tools a request is likely to need.

Why this exists. Mike sends the model every tool's description with every
request: 36 tools, about 6,000 tokens. Measured on an M-series Mac, the model
re-reads all of it each time -- even for an identical request, which was not
cached -- and that costs about 4 seconds per step with a fast GPU. On a
laptop without one (roughly 15 tokens a second) it is several minutes per step.
Most requests are chat, a search or a file job and need none of the heaviest
tools (the document and presentation builders alone are ~1,700 tokens).

The rule that keeps this safe: **when in doubt, offer more.** A tool that is
not offered is a tool the model cannot use, so a missed match is worse than a
wasted few hundred tokens. Hence:

  * everyday tools are always offered;
  * a specialist group is offered if the request, the last few things the
    user said, or anything already used in this conversation points at it;
  * the matching is deliberately generous (a stray "app" or "see" offers the
    screen tools);
  * cloud (Fast mode) calls never come through here -- extra tools cost
    nothing there.

Switch off with MIKE_ROUTE_TOOLS=0 (for comparing before and after).
"""
from __future__ import annotations

import os
import re
from collections.abc import Iterable

from logs.logger import logger

#: Specialist tools, by the kind of job that needs them. Anything not listed
#: here is "everyday" and always offered.
GROUPS: dict[str, frozenset[str]] = {
    "documents": frozenset({
        "create_document", "pdf_edit", "create_presentation",
        "search_document", "document_info", "write_document_section",
    }),
    "spreadsheet": frozenset({"edit_spreadsheet", "read_spreadsheet"}),
    "email": frozenset({"send_email"}),
    "screen": frozenset({
        "click_element", "type_text", "press_keys", "scroll_ui", "see_ui",
        "focus_app", "list_windows", "see_screen",
    }),
}

#: What points at each group. Generous on purpose.
_PATTERNS: dict[str, re.Pattern[str]] = {
    "documents": re.compile(
        # "word" alone is just a word ("containing exactly the word hello");
        # it only means Microsoft Word next to "microsoft"/"ms" or "document".
        r"\b((microsoft|ms) word|word (doc|docs|document|documents|file)|"
        r"pdfs?|docx?|documents?|report|essay|paper|assignment|presentation|"
        r"slides?|deck|pptx?|powerpoint|cover page|title page|contents|apa|mla|ieee|"
        r"citations?|references?|bibliograph\w*|abstract|resume|cv|letter|proposal|"
        r"notes?|summar\w+|page|pages|ocr|scan(ned)?)\b|\.(pdf|docx?|pptx?)\b",
        re.I),
    "spreadsheet": re.compile(
        r"\b(excel|spreadsheets?|xlsx?|csv|sheets?|cells?|columns?|rows?|formulas?|"
        r"pivot|table|tabulate|budget|marks|grades)\b|\.(xlsx?|csv)\b", re.I),
    "email": re.compile(
        r"\b(e-?mails?|gmail|inbox|mail|send (it |this |that )?to|cc|bcc|draft|reply)\b", re.I),
    "screen": re.compile(
        r"\b(click|double[- ]?click|type|typing|press|scroll|windows?|screens?|screenshots?|"
        r"desktop|tabs?|buttons?|menus?|apps?|applications?|focus|switch|drag|dropdown|"
        r"form|fill|log ?in|sign ?in|see|look|show me|watch|visible|open)\b", re.I),
}

#: How many of the user's most recent messages count as "the conversation so
#: far" -- so a follow-up like "yes, do it" keeps what the last request needed.
RECENT_USER_MESSAGES = 3


def enabled() -> bool:
    return os.environ.get("MIKE_ROUTE_TOOLS", "1").strip() != "0"


def _tool_name(tool: dict) -> str:
    return (tool.get("function") or tool).get("name", "")


def _text_of(message: dict) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # multimodal parts
        return " ".join(str(p.get("text", "")) for p in content if isinstance(p, dict))
    return ""


def _used_tool_names(history: Iterable[dict]) -> set[str]:
    used: set[str] = set()
    for message in history:
        for call in message.get("tool_calls") or []:
            name = (call.get("function") or call).get("name")
            if name:
                used.add(name)
    return used


def wanted_groups(history: list[dict]) -> set[str]:
    """Which specialist groups this conversation points at right now."""
    user_texts = [_text_of(m) for m in history if m.get("role") == "user"]
    recent = " \n ".join(user_texts[-RECENT_USER_MESSAGES:])
    used = _used_tool_names(history)

    wanted = {name for name, pattern in _PATTERNS.items() if pattern.search(recent)}
    wanted |= {name for name, tools in GROUPS.items() if tools & used}
    return wanted


def route(tools: list[dict], history: list[dict]) -> list[dict]:
    """`tools` narrowed to what this request is likely to need, in the
    original order (the order is part of what a model has learned to expect)."""
    if not enabled() or not tools:
        return tools

    wanted = wanted_groups(history)
    held_back = {
        name for group, members in GROUPS.items() if group not in wanted for name in members
    }
    if not held_back:
        return tools

    offered = [t for t in tools if _tool_name(t) not in held_back]
    if len(offered) == len(tools):
        return tools
    logger.info("Tools offered: %d of %d (specialist groups: %s)",
                len(offered), len(tools), ", ".join(sorted(wanted)) or "none")
    return offered
