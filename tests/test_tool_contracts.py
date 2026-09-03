"""Regression tests for tool contracts that the agent depends on.

These exist because a mismatch between a tool's declared signature and its
implementation is invisible until the model tries the natural call and fails.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.core_tools import DISPATCH, TOOL_DECLARATIONS, needs_confirmation
from core.tool_executor import ToolExecutor

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))
    if not ok:
        failures.append(label)


executor = ToolExecutor()
sandbox = tempfile.mkdtemp(prefix="mike-contracts-")

try:
    # ── create_file: the contract that used to be broken ─────
    empty_path = os.path.join(sandbox, "empty.txt")
    result = executor.execute(tool_name="filesystem", action="create_file", path=empty_path)
    check(
        "create_file(path) creates an empty file",
        result.success and os.path.exists(empty_path) and open(empty_path).read() == "",
        result.error or "",
    )

    content_path = os.path.join(sandbox, "page.html")
    body = "<h1>Hello</h1>\n"
    result = executor.execute(
        tool_name="filesystem", action="create_file", path=content_path, content=body
    )
    check(
        "create_file(path, content) writes the content",
        result.success and os.path.exists(content_path) and open(content_path).read() == body,
        result.error or "",
    )

    nested = os.path.join(sandbox, "deep", "nested", "file.txt")
    result = executor.execute(
        tool_name="filesystem", action="create_file", path=nested, content="x"
    )
    check(
        "create_file creates missing parent folders",
        result.success and os.path.exists(nested),
        result.error or "",
    )

    # The declaration has to advertise content, or the model never passes it.
    decl = next(d for d in TOOL_DECLARATIONS if d.name == "create_file")
    props = (decl.parameters_json_schema or {}).get("properties", {})
    check("create_file declaration advertises content", "content" in props)
    check("create_file declaration requires only path",
          (decl.parameters_json_schema or {}).get("required") == ["path"])

    # ── run_command: must not hang forever ───────────────────
    from tools.terminal import actions as terminal_actions

    check("run_command has a finite default timeout",
          terminal_actions.DEFAULT_TIMEOUT > 0,
          f"{terminal_actions.DEFAULT_TIMEOUT}s")

    started = time.time()
    try:
        terminal_actions.run("sleep 5", timeout=2)
        timed_out = False
    except RuntimeError as exc:
        timed_out = "still running" in str(exc)
    elapsed = time.time() - started
    check("run_command stops a command that overruns its timeout",
          timed_out and elapsed < 4, f"{elapsed:.1f}s")

    result = executor.execute(tool_name="terminal", action="run", command="echo hi")
    check("run_command still returns output", result.success and "hi" in str(result.data))

    result = executor.execute(
        tool_name="terminal", action="run", command="pwd", cwd=sandbox
    )
    check("run_command honours cwd", result.success and sandbox in str(result.data))

    # ── run_background: long-running processes ───────────────
    result = executor.execute(
        tool_name="terminal",
        action="run_background",
        command="sleep 30",
        cwd=sandbox,
    )
    check("run_background returns while the process keeps running",
          result.success and "still running" in (str(result.data) + str(result.message)),
          result.error or "")

    result = executor.execute(
        tool_name="terminal",
        action="run_background",
        command="exit 3",
    )
    check("run_background reports a process that dies immediately",
          not result.success, result.error or "")

    # ── open_application: generic, not app-specific ──────────
    check("open_application is dispatchable", "open_application" in DISPATCH)
    result = executor.execute(
        tool_name="system", action="open_application", name="NotARealApp_zzz"
    )
    check("open_application fails cleanly for a missing app", not result.success)

    # ── safety gates ─────────────────────────────────────────
    check("run_background requires confirmation", needs_confirmation("run_background", {}))
    check("run_command still requires confirmation", needs_confirmation("run_command", {}))
    check("write_file still requires confirmation", needs_confirmation("write_file", {}))
    check("delete_path still requires confirmation", needs_confirmation("delete_path", {}))
    check("ide_apply_edit still requires confirmation", needs_confirmation("ide_apply_edit", {}))
    check("create_file does NOT require confirmation", not needs_confirmation("create_file", {}))
    check("open_application does NOT require confirmation",
          not needs_confirmation("open_application", {}))

finally:
    shutil.rmtree(sandbox, ignore_errors=True)
    subprocess.run("pkill -f 'sleep 30'", shell=True, capture_output=True)

print()
if failures:
    print(f"{len(failures)} FAILURE(S): {failures}")
    sys.exit(1)

print("ALL TOOL CONTRACT TESTS PASSED")
