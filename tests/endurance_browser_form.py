"""Real agent test: fill a web form through the general computer layer.

This is the capability underneath every workflow the milestone asks for --
email, spreadsheet, cross-application. All of them are the same loop: look at
an interface, find the right control, put something in it, check it took.

Nothing here is browser-specific on Mike's side. The agent gets the same
see_ui / click_element / type_text primitives it uses on native apps, and the
accessibility tree happens to describe web pages too.

Verification reads the form's own state back out of the browser afterwards,
never the model's account of what it did.

    venv/bin/python tests/endurance_browser_form.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MIKE_DATA_DIR", str(Path.home() / ".mike-brain-lab"))

TIME_BUDGET = 2400
FORM = Path(__file__).parent / "fixtures" / "registration_form.html"

TASK = """Open the file {url} in Safari and fill in the registration form for me.

Use these details:
- Full name: Jordan Lee
- Role: Manager
- Bio: Backend engineer, ten years on payments systems.
- Accept the terms
- Choose the Pro plan

The email field is already filled in — leave it alone.

Do NOT submit the form. I want to review it myself first. Just fill it in and
tell me what you set.

The page is a normal web page, so you can read its controls the same way you
read any other application's."""


FIELDS = """<!doctype html><meta charset="utf-8"><title>Mike Registration Form</title>
<style>body{font:16px system-ui;max-width:640px;margin:40px auto}
label{display:block;margin:14px 0 4px}input,select,textarea{width:100%;padding:8px}
button{padding:10px 18px;margin-right:8px}</style>
<h1>Registration</h1>
<form id="f" onsubmit="return false">
<label for="nm">Full name</label><input id="nm" type="text">
<label for="em">Email address</label><input id="em" type="email" value="pre@filled.com">
<label for="rl">Role</label>
<select id="rl"><option>Engineer</option><option>Designer</option><option>Manager</option></select>
<label for="bio">Bio</label><textarea id="bio" rows="3"></textarea>
<label><input type="checkbox" id="tos"> I accept the terms</label>
<label><input type="radio" name="plan" id="p1" checked> Free</label>
<label><input type="radio" name="plan" id="p2"> Pro</label>
<button type="button" id="save">Save draft</button>
<button type="submit" id="send">Submit application</button>
</form>"""


def verify() -> list[tuple[str, bool, str]]:
    """Read the form back out of Safari itself."""
    from computer.session import ComputerSession

    session = ComputerSession()
    result = session.observe(app="Safari", limit=200)
    checks: list[tuple[str, bool, str]] = []
    if result["status"] != "success":
        return [("the form is observable", False, result.get("error", "?"))]

    elements = session._observation.elements
    by_label = {(e.label or "").strip().lower(): e for e in elements}

    def field(name):
        return by_label.get(name)

    name = field("full name")
    checks.append(("full name was typed", bool(name and "Jordan Lee" in (name.value or "")),
                   f"value={name.value!r}" if name else "field not found"))

    bio = field("bio")
    checks.append(("bio was typed", bool(bio and (bio.value or "").strip()),
                   f"value={(bio.value or '')[:50]!r}" if bio else "field not found"))

    role = field("role")
    checks.append(("role set to Manager", bool(role and "Manager" in (role.value or "")),
                   f"value={role.value!r}" if role else "field not found"))

    tos = field("i accept the terms")
    checks.append(("terms accepted", bool(tos and str(tos.value) in ("1", "true", "True")),
                   f"value={tos.value!r}" if tos else "field not found"))

    pro = field("pro")
    checks.append(("Pro plan selected", bool(pro and str(pro.value) in ("1", "true", "True")),
                   f"value={pro.value!r}" if pro else "field not found"))

    email = field("email address")
    checks.append(("pre-filled email left untouched",
                   bool(email and (email.value or "") == "pre@filled.com"),
                   f"value={email.value!r}" if email else "field not found"))
    return checks


def main() -> None:
    from brain.core_runtime import CoreRuntime

    FORM.parent.mkdir(parents=True, exist_ok=True)
    FORM.write_text(FIELDS)
    subprocess.run(["open", "-a", "Safari", f"file://{FORM}"], check=True)
    time.sleep(4)

    runtime = CoreRuntime()
    brain = runtime._brain_capabilities().model

    calls: list[dict] = []
    original = runtime._execute_tool

    def recording(name, args):
        started = time.time()
        result = original(name, args)
        calls.append({
            "n": len(calls) + 1, "tool": name,
            "args": {k: str(v)[:80] for k, v in (args or {}).items()},
            "status": result.get("status", "?") if isinstance(result, dict) else "?",
            "ms": round((time.time() - started) * 1000),
        })
        return result

    runtime._execute_tool = recording

    turns = [0]
    original_loop = runtime._streaming_loop

    def counting(cb, ce, depth=0):
        turns[0] += 1
        yield from original_loop(cb, ce, depth)

    runtime._streaming_loop = counting

    confirmations: list[str] = []

    def confirm(detail):
        confirmations.append(str(detail))
        return False        # nothing irreversible should be needed here

    print(f"brain : {brain}\nform  : file://{FORM}\n")
    started = time.time()
    reply, stopped = "", ""
    try:
        for kind, payload in runtime.process_streaming(
            TASK.format(url=f"file://{FORM}"), confirm_callback=confirm
        ):
            if kind == "token":
                reply += payload
            elif kind == "tool_start":
                print(f"  [{len(calls) + 1:2}] {payload[:76]}", flush=True)
            if time.time() - started > TIME_BUDGET:
                stopped = "exceeded the time budget"
                break
    except Exception as exc:
        stopped = f"{type(exc).__name__}: {exc}"

    elapsed = round(time.time() - started)
    results = verify()
    passed = sum(1 for _, ok, _ in results if ok)

    counts: dict[str, int] = {}
    for call in calls:
        counts[call["tool"]] = counts.get(call["tool"], 0) + 1

    print(f"\n{'=' * 60}\nTRAJECTORY")
    print(f"  llm turns      : {turns[0]}")
    print(f"  tool calls     : {len(calls)}")
    print(f"  tools used     : {counts}")
    print(f"  vision calls   : {counts.get('see_screen', 0)}")
    print(f"  confirmations  : {len(confirmations)} {confirmations[:2]}")
    print(f"  elapsed        : {elapsed}s")
    if stopped:
        print(f"  stopped early  : {stopped}")

    print(f"\nINDEPENDENT VERIFICATION ({passed}/{len(results)})")
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}\n        {detail}")

    print(f"\nMODEL'S CLAIM (not evidence):\n  {reply.strip()[-300:]!r}")

    out = Path(__file__).parent.parent / "design" / f"browser_form_{brain.replace(':', '_')}.json"
    out.write_text(json.dumps({
        "brain": brain, "seconds": elapsed, "llm_turns": turns[0],
        "tool_calls": calls, "tools_used": counts,
        "confirmations": confirmations, "stopped_early": stopped,
        "verification": [{"check": n, "passed": o, "detail": d} for n, o, d in results],
        "reply": reply[-1500:],
    }, indent=2))
    print(f"\nevidence: {out}")


if __name__ == "__main__":
    main()
