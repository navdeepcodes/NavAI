"""Does Mike understand what "it" means? Run by hand against the real model.

Not a pytest test. It talks to the live brain, so it is slow, and it is scored
rather than asserted — a local model is allowed an occasional miss, and a
pass/fail gate on one sample would be noise.

Nothing is executed. Each scenario builds a real conversation, asks the real
model with the real tool surface, and reads back *the tool call it chose* or
*the sentence it wrote*. Reference resolution is entirely visible at that
point, and no file is written, no app is opened and no mail is sent.

    venv/bin/python tests/reference_probe.py

Two kinds of scenario, and both matter:

  resolve   the reference has one sensible answer; Mike should act on it
  ask       the reference is genuinely ambiguous; Mike should ask, not guess

The second is the one worth protecting. Confident nonsense is much worse than
a short question, and a model that always guesses will look fine on the first
kind while being untrustworthy in use.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401

from brain.context_budget import plan_request
from brain.core_runtime import OLLAMA_TOOLS, SYSTEM_PROMPT
from brain.providers import get_provider


def _u(text):
    return {"role": "user", "content": text}


def _a(text):
    return {"role": "assistant", "content": text}


def _tool_turn(call_id, name, args, result):
    """A completed tool exchange, shaped exactly as the runtime records it."""
    return [
        {"role": "assistant", "content": "",
         "tool_calls": [{"id": call_id,
                         "function": {"name": name, "arguments": args}}]},
        {"role": "tool", "tool_call_id": call_id,
         "content": json.dumps(result)},
    ]


# Each scenario: history, the referring message, and what a correct answer
# looks like. `expect_ask` scenarios are ambiguous on purpose.
SCENARIOS = [
    {
        "name": "rename the thing we named",
        "history": [_u("Let's call the project Apollo."),
                    _a("Got it — Apollo it is.")],
        "message": "Change its name to Nova.",
        "must_mention": ["apollo"],
        "expect_ask": False,
        "why": "'its' is the project we just named",
    },
    {
        "name": "open the project we discussed",
        "history": [_u("I'm working on Project Apollo today."),
                    _a("Sounds good — what do you need?")],
        "message": "Open it.",
        "must_mention": ["apollo"],
        "expect_ask": False,
        "why": "'it' is Apollo",
    },
    {
        "name": "change the recipient, keep the attachment",
        "history": [_u("Email the Q3 budget spreadsheet to John."),
                    _a("Sent the Q3 budget spreadsheet to John.")],
        "message": "Actually, send it to Sarah instead.",
        "must_mention": ["sarah"],
        "must_not_mention": ["john"],
        "expect_ask": False,
        "why": "'it' is the Q3 budget spreadsheet; the recipient changes",
    },
    {
        "name": "recall a decision made in conversation",
        "history": [_u("Use Qwen for the summariser, not Llama."),
                    _a("Understood — Qwen for the summariser.")],
        "message": "Why did we choose it?",
        "must_mention": ["qwen"],
        "expect_ask": False,
        "why": "'it' is Qwen",
    },
    {
        "name": "close what we opened",
        "history": [_u("Open Safari and go to the Apple site."),
                    *_tool_turn("c1", "open_application", {"name": "Safari"},
                                {"status": "ok", "result": "Opened Safari"}),
                    _a("Safari's open on apple.com.")],
        "message": "Now close it.",
        "must_mention": ["safari"],
        "expect_ask": False,
        "why": "'it' is Safari",
    },
    {
        "name": "a preference stated earlier",
        "history": [_u("Remember that Mike's voice should be Ryan."),
                    *_tool_turn("c2", "remember", {"content": "Voice should be Ryan"},
                                {"status": "ok", "result": "Saved"}),
                    _a("Got it, I'll remember that.")],
        "message": "What voice did I choose?",
        "must_mention": ["ryan"],
        "expect_ask": False,
        "why": "stated two turns ago",
    },
    {
        "name": "AMBIGUOUS: which file goes in the folder",
        "history": [_u("Create a folder called Research."),
                    *_tool_turn("c3", "create_folder", {"name": "Research"},
                                {"status": "ok", "result": "Created Research"}),
                    _a("Created the Research folder.")],
        "message": "Put the file there.",
        "expect_ask": True,
        "why": "no file has ever been mentioned — Mike must ask which one",
    },
    {
        "name": "AMBIGUOUS: two similar reports",
        "history": [_u("I have two reports open: report-2024.pdf and report-2025.pdf."),
                    _a("Got it — both are open.")],
        "message": "Delete the other one.",
        "expect_ask": True,
        "why": "'the other one' has no antecedent — neither was singled out",
    },
]

ASKING = ("which", "what ", "?", "could you clarify", "do you mean",
          "not sure", "you mean")


def _describe(result) -> str:
    """Everything the model committed to this turn, as one lowercase string."""
    parts = [result.text or ""]
    for call in (result.tool_calls or []):
        parts.append(call.name)
        parts.append(json.dumps(call.arguments or {}))
    return " ".join(parts).lower()


def run() -> None:
    provider = get_provider()
    caps = provider.capabilities()
    print(f"model: {caps.model}  (max input {caps.max_input_tokens:,} tokens)\n")

    passed = 0
    for scenario in SCENARIOS:
        history = [*scenario["history"], _u(scenario["message"])]
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history]
        plan = plan_request(messages, OLLAMA_TOOLS, caps)

        result = provider.complete(plan.messages, plan.tools)
        if result.error is not None:
            print(f"  ERROR {scenario['name']}: {result.error.detail}")
            continue

        said = _describe(result)
        asked = any(marker in said for marker in ASKING)

        if scenario["expect_ask"]:
            ok = asked and not (result.tool_calls or [])
            verdict = "asked" if ok else "GUESSED"
        else:
            ok = all(m in said for m in scenario.get("must_mention", []))
            for banned in scenario.get("must_not_mention", []):
                if banned in said:
                    ok = False
            verdict = "resolved" if ok else "MISSED"

        passed += bool(ok)
        print(f"[{'PASS' if ok else 'FAIL'}] {scenario['name']}  -> {verdict}")
        print(f"        why: {scenario['why']}")
        print(f"        dropped {plan.dropped_history} msg(s), "
              f"{len(plan.tools or [])} tools offered")
        preview = (result.text or "").strip().replace("\n", " ")[:110]
        if result.tool_calls:
            for call in result.tool_calls:
                print(f"        call: {call.name}({json.dumps(call.arguments)[:90]})")
        if preview:
            print(f"        said: {preview}")
        print()

    print(f"=== {passed}/{len(SCENARIOS)} scenarios correct ===")


if __name__ == "__main__":
    run()
