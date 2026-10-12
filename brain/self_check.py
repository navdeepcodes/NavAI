"""`Mike --self-check`: does this build have the tools it is supposed to have?

Two real releases shipped without some of Mike's tools and nothing noticed:
the registry finds tools by walking the package at runtime, so a packaging
mistake leaves the app starting normally while every web search, "open an
app" and terminal command fails with "Unknown tool: ...". Mike then retried
the dead call until the step limit and showed a green tick for each attempt.

This runs the same registry the app uses, with no window and no model, and
exits non-zero if a tool is missing. It is meant for the release process to
run on the *built* app, not on the source tree:

    Mike.exe --self-check C:\\path\\report.json
    Mike.app/Contents/MacOS/Mike --self-check /path/report.json

The path is optional; the report is also printed when there is a console.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

#: What a complete build registers. Add a name here when a tool package is
#: added, so forgetting to ship it fails the release instead of the user.
EXPECTED_TOOLS = frozenset({"browser", "email", "filesystem", "ide", "system", "terminal"})


def check() -> dict:
    """Load the real tool registry and compare it with what must be there."""
    report: dict = {"ok": False, "tools": [], "missing": [], "error": None,
                    "frozen": bool(getattr(sys, "frozen", False))}
    try:
        from config.settings import VERSION
        report["version"] = VERSION
        from tools.tool_registry import ToolRegistry

        names = sorted(ToolRegistry().tools)
        report["tools"] = names
        report["missing"] = sorted(EXPECTED_TOOLS - set(names))
        report["ok"] = not report["missing"]
    except Exception as exc:  # a build that can't even import is a failed check
        report["error"] = f"{type(exc).__name__}: {exc}"
    return report


def run(args: list[str]) -> int:
    """Entry point for main.py. `args` is whatever followed --self-check."""
    report = check()
    text = json.dumps(report, indent=2)
    if args:
        try:
            Path(args[0]).write_text(text, encoding="utf-8")
        except OSError as exc:
            report["ok"] = False
            text = json.dumps({**report, "error": f"could not write {args[0]}: {exc}"}, indent=2)
    # A windowed Windows build has no stdout at all.
    if sys.stdout is not None:
        print(text)
    return 0 if report["ok"] else 1
