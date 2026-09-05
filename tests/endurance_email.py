"""Real agent test: find a file, compose, attach, confirm, send, verify.

The agent is given a goal and the general tool set. It is not told which
mechanism to use -- send_email is simply one of the tools it has, alongside
the filesystem and computer-control primitives. Nothing here sequences the
workflow.

Two things make the result trustworthy.

**Confirmation is real.** The callback below stands in for the user at the one
irreversible step. It does not rubber-stamp: it independently checks that the
recipient is the intended one and that the attachment exists on disk with the
expected contents, and refuses otherwise. A run that tries to send without a
real attachment fails here rather than passing.

**Verification reads the mailbox.** After sending, the message is fetched back
from Gmail and its recipient, subject and attachment filenames are read from
what the server actually stored -- never from the model's account of what it
did, and never from the returned message id, which only proves a request was
accepted.

    venv/bin/python tests/endurance_email.py [--steps N]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MIKE_DATA_DIR", str(Path.home() / ".mike-brain-lab"))

TIME_BUDGET = 2400
REPORT = Path.home() / "mike-email-task" / "quarterly_report.txt"
def _recipient() -> str:
    """Where a real run sends its mail.

    Read from the environment rather than written down here. This repository
    is public, and a person's mailbox is not part of the test — anyone
    running this should point it at their own:

        MIKE_TEST_RECIPIENT=you@example.com venv/bin/python tests/endurance_email.py
    """
    address = os.environ.get("MIKE_TEST_RECIPIENT", "").strip()
    if not address:
        raise SystemExit(
            "Set MIKE_TEST_RECIPIENT to the address this run should mail, "
            "e.g. MIKE_TEST_RECIPIENT=you@example.com"
        )
    return address


RECIPIENT = _recipient()
SUBJECT_TOKEN = "Q3 Engineering Report"

TASK = f"""Please email me the quarterly report.

The file is somewhere under {REPORT.parent} — find it first, and read it so
you can describe it accurately.

Send it to {RECIPIENT} with the subject "{SUBJECT_TOKEN}". In the body, write
two or three sentences summarising what the report actually says. Attach the
report file to the message.

Make sure the attachment is really on the message before you send it."""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=int, default=None)
    args = parser.parse_args()

    import brain.core_runtime as core_runtime
    from brain.core_runtime import CoreRuntime

    default_steps = core_runtime.MAX_AGENT_STEPS
    if args.steps:
        core_runtime.MAX_AGENT_STEPS = args.steps

    assert REPORT.exists(), f"report missing at {REPORT}"
    expected_marker = "QUARTERLY ENGINEERING REPORT"

    runtime = CoreRuntime()
    brain = runtime._brain_capabilities().model

    calls: list[dict] = []
    original = runtime._execute_tool

    def recording(name, tool_args):
        started = time.time()
        result = original(name, tool_args)
        calls.append({
            "n": len(calls) + 1, "tool": name,
            "args": {k: str(v)[:120] for k, v in (tool_args or {}).items()},
            "status": result.get("status", "?") if isinstance(result, dict) else "?",
            "ms": round((time.time() - started) * 1000),
            "result": str(result.get("result", result.get("error", "")))[:400]
                      if isinstance(result, dict) else "",
        })
        return result

    runtime._execute_tool = recording

    turns = [0]
    original_loop = runtime._streaming_loop

    def counting(cb, ce, depth=0):
        turns[0] += 1
        yield from original_loop(cb, ce, depth)

    runtime._streaming_loop = counting

    decisions: list[dict] = []
    pending: dict = {}

    original_confirm_check = core_runtime.needs_confirmation

    def watch_args(name, tool_args):
        # Capture what is about to be confirmed, so the callback can judge the
        # actual arguments rather than a description of them.
        if name == "send_email":
            pending.clear()
            pending.update(tool_args or {})
        return original_confirm_check(name, tool_args)

    core_runtime.needs_confirmation = watch_args

    def confirm(detail: str) -> bool:
        """Stand in for the user at the irreversible step."""
        to = str(pending.get("to") or "")
        attachments = [str(a) for a in (pending.get("attachments") or [])]

        recipient_ok = to.strip().lower() == RECIPIENT.lower()
        attachment_ok = False
        attachment_note = "no attachment given"
        for path in attachments:
            resolved = Path(os.path.expanduser(path))
            if resolved.is_file():
                try:
                    content = resolved.read_text(errors="replace")
                except Exception:
                    content = ""
                if expected_marker in content:
                    attachment_ok = True
                    attachment_note = f"{resolved.name} exists and is the report"
                else:
                    attachment_note = f"{resolved.name} exists but is not the report"
            else:
                attachment_note = f"{path} does not exist"

        allow = recipient_ok and attachment_ok
        decisions.append({
            "detail": str(detail)[:400], "to": to, "attachments": attachments,
            "recipient_ok": recipient_ok, "attachment_ok": attachment_ok,
            "attachment_note": attachment_note, "allowed": allow,
            "at_tool_call": len(calls),
        })
        print("\n  >> CONFIRMATION REQUESTED")
        for line in str(detail).splitlines():
            print(f"     {line}")
        print(f"     recipient_ok={recipient_ok} attachment_ok={attachment_ok} "
              f"({attachment_note}) -> {'ALLOW' if allow else 'DENY'}\n", flush=True)
        return allow

    print(f"brain     : {brain}")
    print(f"step cap  : {core_runtime.MAX_AGENT_STEPS}"
          + (" (raised for this run)" if args.steps else " (default)"))
    print(f"report    : {REPORT}")
    print(f"recipient : {RECIPIENT}\n")

    started = time.time()
    reply, stopped = "", ""
    try:
        for kind, payload in runtime.process_streaming(TASK, confirm_callback=confirm):
            if kind == "token":
                reply += payload
            elif kind == "tool_start":
                print(f"  [{len(calls) + 1:2}] {payload[:74]}", flush=True)
            if time.time() - started > TIME_BUDGET:
                stopped = "exceeded the time budget"
                break
    except Exception as exc:
        stopped = f"{type(exc).__name__}: {exc}"

    elapsed = round(time.time() - started)

    # ── independent verification, from the mailbox ────────────────
    sent_call = next((c for c in calls if c["tool"] == "send_email"
                      and c["status"] == "success"), None)
    verified: dict = {}
    if sent_call:
        try:
            from tools.email.gmail_client import GmailClient
            import re as _re
            match = _re.search(r"id ([0-9a-f]+)|message_id", sent_call.get("result", ""))
            # The runtime already read it back; re-read here independently.
            client = GmailClient()
            listing = client.service.users().messages().list(
                userId="me", q=f'subject:"{SUBJECT_TOKEN}" in:sent', maxResults=1,
            ).execute()
            ids = [m["id"] for m in listing.get("messages", [])]
            if ids:
                verified = client.describe_sent(ids[0])
        except Exception as exc:
            verified = {"error": str(exc)[:200]}

    checks = [
        ("the agent asked before sending", bool(decisions),
         f"{len(decisions)} confirmation(s) requested"),
        ("the confirmation named the real recipient and attachment",
         bool(decisions and decisions[-1]["recipient_ok"] and decisions[-1]["attachment_ok"]),
         decisions[-1]["attachment_note"] if decisions else "never asked"),
        ("a message was actually sent", bool(sent_call),
         sent_call["result"][:160] if sent_call else "send_email never succeeded"),
        ("the mailbox shows the right recipient",
         verified.get("to", "").find(RECIPIENT) >= 0,
         f"to={verified.get('to')!r}"),
        ("the mailbox shows the attachment",
         REPORT.name in (verified.get("attachments") or []),
         f"attachments={verified.get('attachments')}"),
        ("the message is in Sent", bool(verified.get("in_sent")),
         f"labels={verified.get('labels')}"),
    ]
    passed = sum(1 for _, ok, _ in checks if ok)

    counts: dict[str, int] = {}
    for call in calls:
        counts[call["tool"]] = counts.get(call["tool"], 0) + 1

    print(f"\n{'=' * 62}\nTRAJECTORY")
    print(f"  llm turns      : {turns[0]}")
    print(f"  tool calls     : {len(calls)}")
    print(f"  tools used     : {counts}")
    print(f"  vision calls   : {counts.get('see_screen', 0)}")
    print(f"  confirmations  : {len(decisions)}")
    print(f"  elapsed        : {elapsed}s")
    if stopped:
        print(f"  stopped early  : {stopped}")

    print(f"\nINDEPENDENT VERIFICATION ({passed}/{len(checks)})")
    for name, ok, detail in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}\n        {detail}")

    print(f"\nMODEL'S CLAIM (not evidence):\n  {reply.strip()[-350:]!r}")

    out = Path(__file__).parent.parent / "design" / f"email_workflow_{brain.replace(':', '_')}.json"
    out.write_text(json.dumps({
        "brain": brain, "seconds": elapsed, "llm_turns": turns[0],
        "step_cap": core_runtime.MAX_AGENT_STEPS, "default_step_cap": default_steps,
        "tool_calls": calls, "tools_used": counts, "confirmations": decisions,
        "mailbox_verification": verified,
        "checks": [{"check": n, "passed": o, "detail": d} for n, o, d in checks],
        "stopped_early": stopped, "reply": reply[-1500:],
    }, indent=2))
    print(f"\nevidence: {out}")


if __name__ == "__main__":
    main()
