"""Every model-facing tool, checked against its own declared contract.

Mike declares 41 tools. Six of them had no test at all, and a sweep of the
whole surface found 18 places where a call that could not succeed was
accepted anyway -- unknown parameters swallowed, and strings accepted for
parameters declared as integers or arrays.

Both matter for the same reason: a call that is accepted and then fails deep
inside execution costs the model a step and tells it nothing useful, and a
parameter that is silently dropped makes the tool do something other than
what was asked. That is not hypothetical -- run_command once took `path`
instead of `cwd`, dropped it, and executed in Mike's own source tree.

These are contract tests. They read the schemas the model is actually given,
so a new tool is covered the day it is declared.
"""
from __future__ import annotations

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401


def _declared():
    from brain.core_tools import OLLAMA_TOOLS
    return [t["function"] for t in OLLAMA_TOOLS]


def _runtime():
    from brain.core_runtime import CoreRuntime
    return CoreRuntime()


# ══ the contract holds for every tool, present and future ══

def test_no_tool_accepts_an_unknown_parameter():
    from brain.core_tools import check_arguments

    offenders = []
    for fn in _declared():
        schema = fn.get("parameters") or {}
        required = schema.get("required") or []
        args = {r: "x" for r in required}
        args["definitely_not_a_real_parameter"] = 1
        if check_arguments(fn["name"], args) is None:
            offenders.append(fn["name"])

    assert not offenders, (
        f"these tools swallow unknown parameters: {offenders}. A dropped "
        "parameter makes the tool do something other than what was asked."
    )
    print(f"PASS: all {len(_declared())} tools refuse unknown parameters")


def test_no_tool_accepts_a_value_of_the_wrong_type():
    from brain.core_tools import check_arguments

    offenders = []
    for fn in _declared():
        schema = fn.get("parameters") or {}
        required = schema.get("required") or []
        for name, spec in (schema.get("properties") or {}).items():
            want = spec.get("type")
            if want not in ("integer", "number", "array"):
                continue
            args = {r: "x" for r in required}
            args[name] = "definitely-not-that-type"
            if check_arguments(fn["name"], args) is None:
                offenders.append(f"{fn['name']}.{name} ({want})")
    assert not offenders, f"wrong types accepted: {offenders}"
    print("PASS: declared types are enforced")


def test_every_required_parameter_is_actually_required():
    from brain.core_tools import check_arguments

    offenders = [fn["name"] for fn in _declared()
                 if (fn.get("parameters") or {}).get("required")
                 and check_arguments(fn["name"], {}) is None]
    assert not offenders, f"these accept missing required arguments: {offenders}"
    print("PASS: required parameters are enforced")


def test_a_numeric_string_is_accepted_where_a_number_is_wanted():
    """Refusing "30" for a timeout would be pedantry, not safety: it converts
    losslessly and models produce it constantly. Only values that cannot be
    the declared type are refused."""
    from brain.core_tools import check_arguments

    assert check_arguments("run_command", {"command": "ls", "timeout": "30"}) is None
    assert check_arguments("kill_process", {"pid": "123"}) is None
    assert check_arguments("kill_process", {"pid": "soon"}) is not None
    print("PASS: lossless coercion is allowed, guessing is not")


def test_every_declared_tool_can_be_dispatched():
    """A tool the model is offered but the runtime cannot route is a dead end
    it will spend a step discovering."""
    from brain.core_runtime import _COMPUTER_TOOLS, _DIRECT_TOOLS, _SPECIAL_TOOLS
    from brain.core_tools import DISPATCH, MEMORY_TOOLS

    # Every routing table the runtime actually consults, read from the
    # runtime. This used to carry a hand-written list of the specially-routed
    # names alongside it, which meant adding a tool made the test fail for a
    # bookkeeping reason rather than a real one.
    routed = (set(DISPATCH) | set(MEMORY_TOOLS) | set(_DIRECT_TOOLS)
              | set(_COMPUTER_TOOLS) | set(_SPECIAL_TOOLS))
    orphans = [fn["name"] for fn in _declared() if fn["name"] not in routed]
    assert not orphans, f"declared but unroutable: {orphans}"
    print("PASS: every declared tool has an execution path")


# ══ the six that had no coverage at all ════════════════════

def test_create_folder_says_whether_it_created_anything():
    """"Created successfully" for a folder that already existed reads as proof
    the call did something, and a model verifying its own work would believe
    a fresh directory now exists."""
    runtime = _runtime()
    target = os.path.join(tempfile.mkdtemp(), "fresh")

    first = runtime._execute_tool("create_folder", {"path": target})
    assert first["status"] == "success"
    assert "already existed" not in first["result"]

    again = runtime._execute_tool("create_folder", {"path": target})
    assert again["status"] == "success"
    assert "already existed" in again["result"], (
        f"a no-op must not claim to have created anything: {again['result']!r}"
    )
    assert os.path.isdir(target)
    print("PASS: create_folder distinguishes created from already-present")


def test_search_files_finds_by_name_quickly():
    """It used to run `grep -r` from the user's Desktop with a 15s timeout,
    which on a 7.3 GB Desktop is a guaranteed timeout, and duplicated
    search_code badly. It now does what search_code cannot: find by name."""
    import time

    folder = tempfile.mkdtemp()
    open(os.path.join(folder, "quarterly_report.txt"), "w").close()
    open(os.path.join(folder, "notes.md"), "w").close()

    runtime = _runtime()
    started = time.time()
    result = runtime._execute_tool(
        "search_files", {"query": "quarterly", "path": folder})
    elapsed = time.time() - started

    assert result["status"] == "success", result.get("error")
    assert "quarterly_report.txt" in result["result"]
    assert "notes.md" not in result["result"]
    assert elapsed < 10, f"a scoped name search should be fast, took {elapsed:.1f}s"
    print(f"PASS: search_files finds by name in {elapsed:.2f}s")


def test_search_files_points_content_searches_at_search_code():
    """Two tools doing the same job badly is worse than one doing it well."""
    from brain.core_tools import OLLAMA_TOOLS

    declaration = next(t for t in OLLAMA_TOOLS
                       if t["function"]["name"] == "search_files")
    description = declaration["function"]["description"].lower()
    assert "search_code" in description, "it must name the right tool for content"
    assert "name" in description
    print("PASS: search_files and search_code have distinct jobs")


def test_search_files_reports_an_empty_result_honestly():
    runtime = _runtime()
    result = runtime._execute_tool(
        "search_files", {"query": "zzz_nothing_zzz", "path": tempfile.mkdtemp()})
    assert result["status"] == "success"
    assert "No file matching" in result["result"]
    assert "search_code" in result["result"], "point at the alternative"
    print("PASS: an empty name search explains itself")


def test_scroll_without_an_observation_is_refused():
    runtime = _runtime()
    result = runtime._execute_tool("scroll_ui", {"ref": "el7", "dy": -100})
    assert result["status"] == "error"
    assert "see_ui" in result["error"]
    print("PASS: scrolling an unobserved reference is refused")


def test_ide_tools_report_honestly_when_no_editor_is_connected():
    """An integration that is simply not connected must say so, rather than
    failing in a way that looks like the request was wrong."""
    runtime = _runtime()
    for name, args in (("ide_context", {}),
                       ("ide_open_file", {"path": "/tmp/nope.txt"})):
        result = runtime._execute_tool(name, args)
        if result["status"] == "success":
            pytest.skip("an editor is connected on this machine")
        assert "editor" in result["error"].lower(), result["error"]
    print("PASS: IDE tools report a missing editor plainly")


def test_web_search_returns_results_or_a_clear_failure():
    runtime = _runtime()
    result = runtime._execute_tool("search_web", {"query": "boiling point of water"})
    if result["status"] != "success":
        pytest.skip(f"web search unavailable here: {result.get('error','')[:60]}")
    assert result["result"].strip(), "a successful search must return something"
    print("PASS: search_web returns results")


if __name__ == "__main__":
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        fn()
    print("\nAll tool surface tests passed.")
