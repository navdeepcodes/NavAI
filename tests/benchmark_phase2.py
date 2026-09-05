"""Run the representative tasks repeatedly and print one table.

A single passing run tells you a task can work. Three tell you something
about whether it does. This drives the endurance scripts as they are — no
special benchmark path through the runtime, no shortcuts around
confirmation — and reads their evidence files afterwards, so the numbers in
the table come from the same verification the scripts already do.

Failures are reported, never retried silently. A failed run stays in the
table with its verification score, and the classification of why belongs in
the write-up, not in the harness.

    venv/bin/python tests/benchmark_phase2.py --repeats 3
    venv/bin/python tests/benchmark_phase2.py --only spreadsheet,crossapp
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "design" / "evidence"
PYTHON = str(ROOT / "venv" / "bin" / "python")

def _brain_slug() -> str:
    """How the older scripts spell the model in their evidence filenames.

    Read from configuration rather than written down here. A hardcoded
    "qwen3.5_9b" in this file would silently stop finding evidence the day
    the brain changes, and the sweep would report "no evidence written" for
    runs that had in fact succeeded.
    """
    from config.ollama import OLLAMA_CHAT_MODEL

    return OLLAMA_CHAT_MODEL.replace(":", "_")


# label -> (script, extra args, evidence file the script writes)
TASKS = {
    "browser form": ("tests/endurance_browser_form.py", [],
                     ROOT / "design" / f"browser_form_{_brain_slug()}.json"),
    "email": ("tests/endurance_email.py", [],
              ROOT / "design" / f"email_workflow_{_brain_slug()}.json"),
    "spreadsheet": ("tests/endurance_spreadsheet.py", [], None),
    "cross-application": ("tests/endurance_crossapp.py", [], None),
}

# Where the harness-based scripts save, given --run N.
HARNESS_EVIDENCE = {
    "spreadsheet": "spreadsheet_normal_run{n}.json",
    "cross-application": "crossapp_run{n}.json",
}


def metrics(payload: dict) -> dict:
    """Normalise the two evidence shapes into one row's worth of numbers."""
    calls = payload.get("calls") or payload.get("tool_calls") or []
    checks = payload.get("checks") or payload.get("verification") or []
    passed = sum(1 for c in checks if c.get("passed"))

    vision = sum(1 for c in calls if c.get("tool") == "see_screen")
    failed = [c for c in calls if c.get("status") not in ("success", "command_failed")]
    recovered = sum(
        1 for i, c in enumerate(calls)
        if c.get("status") not in ("success", "command_failed")
        and any(l.get("tool") == c.get("tool") and l.get("status") == "success"
                for l in calls[i + 1:])
    )
    return {
        "turns": payload.get("turns") or payload.get("llm_turns") or 0,
        "calls": len(calls),
        "seconds": payload.get("seconds", 0),
        "vision": vision,
        "failed": len(failed),
        "recovered": recovered,
        "passed": passed,
        "total": len(checks),
        "ok": bool(checks) and passed == len(checks),
        "stopped_early": payload.get("stopped_early", ""),
    }


def run_once(label: str, run_number: int) -> dict | None:
    script, extra, fixed_evidence = TASKS[label]
    args = [PYTHON, script, *extra]
    if label in HARNESS_EVIDENCE:
        args += ["--run", str(run_number)]

    print(f"\n{'=' * 68}\n{label} — run {run_number}\n{'=' * 68}", flush=True)
    started = time.time()
    proc = subprocess.run(args, cwd=str(ROOT), capture_output=True, text=True)
    wall = round(time.time() - started)

    tail = "\n".join(
        line for line in (proc.stdout or "").splitlines()
        if line.startswith("  PASS") or line.startswith("  FAIL")
        or line.strip().startswith("turns:")
    )
    print(tail or (proc.stdout or "")[-1200:])
    if proc.returncode != 0:
        print(f"  (exit {proc.returncode}) {(proc.stderr or '')[-400:]}")

    if label in HARNESS_EVIDENCE:
        path = EVIDENCE / HARNESS_EVIDENCE[label].format(n=run_number)
    else:
        path = fixed_evidence
        if path and path.exists():
            kept = EVIDENCE / f"{label.replace(' ', '_')}_run{run_number}.json"
            kept.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(path, kept)
            path = kept

    if not path or not path.exists():
        print(f"  no evidence file at {path}")
        return {"turns": 0, "calls": 0, "seconds": wall, "vision": 0,
                "failed": 0, "recovered": 0, "passed": 0, "total": 0,
                "ok": False, "stopped_early": "no evidence written"}

    return metrics(json.loads(path.read_text()))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--only", default="")
    parser.add_argument("--start", type=int, default=1,
                        help="first run number, for topping up an earlier sweep")
    args = parser.parse_args()

    labels = list(TASKS)
    if args.only:
        wanted = {s.strip().lower() for s in args.only.split(",")}
        labels = [l for l in labels
                  if l.lower() in wanted or l.split()[0].lower() in wanted]

    rows: list[str] = []
    for label in labels:
        for n in range(args.start, args.start + args.repeats):
            m = run_once(label, n)
            rows.append(
                f"| {label} | {n} | {'PASS' if m['ok'] else 'FAIL'} | {m['turns']} "
                f"| {m['calls']} | {m['seconds']}s | {m['vision']} "
                f"| {m['recovered']}/{m['failed']} | {m['passed']}/{m['total']} |"
            )
            print("\n" + rows[-1], flush=True)

    print("\n\n" + "=" * 68)
    print("| Task | Run | Result | Turns | Calls | Time | Vision | Recovery | Verification |")
    print("|---|---:|---|---:|---:|---:|---:|---:|---|")
    for row in rows:
        print(row)

    out = EVIDENCE / "benchmark_table.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "| Task | Run | Result | Turns | Calls | Time | Vision | Recovery | Verification |\n"
        "|---|---:|---|---:|---:|---:|---:|---:|---|\n" + "\n".join(rows) + "\n"
    )
    print(f"\nsaved: {out}")


if __name__ == "__main__":
    main()
