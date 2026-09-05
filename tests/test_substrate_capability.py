"""Can the runtime actually do the benchmark work?

The end-to-end benchmark measures runtime AND model together, and when it
fails the two are easy to confuse. This file isolates the runtime: it drives
the same tool calls a competent model would emit for the same benchmark
tasks, through the same CoreRuntime._execute_tool path, and objectively
verifies the outcome with the benchmark's own verifiers.

If these pass while the benchmark fails, the substrate is capable and the
gap is the model's decision-making. That distinction decides what to fix
next, so it is worth measuring directly rather than inferring.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401


def _rt():
    from brain.core_runtime import CoreRuntime
    return CoreRuntime()


def test_substrate_can_fix_a_bug_and_prove_it():
    """Task 2: run tests, see the real failure, fix it, verify."""
    from tests.benchmark_runtime import setup_bug, verify_bug

    rt = _rt()
    wd = tempfile.mkdtemp()
    setup_bug(wd)

    # 1. observe the failure — this is what used to be impossible
    run = rt._execute_tool("run_command", {"command": f"{sys.executable} -m pytest -q", "cwd": wd})
    assert run["status"] == "command_failed"
    assert run["exit_code"] != 0
    assert "test_add" in run["stdout"], "the failing test must be identifiable from the output"

    # 2. read the source with addressable lines
    read = rt._execute_tool("read_lines", {"path": f"{wd}/calc.py"})
    assert "return a - b" in read["content"]

    # 3. targeted fix
    edit = rt._execute_tool("edit_file", {
        "path": f"{wd}/calc.py", "old_text": "return a - b", "new_text": "return a + b",
    })
    assert edit["status"] == "success"
    assert "+    return a + b" in edit["diff"]

    # 4. verify by re-running
    again = rt._execute_tool("run_command", {"command": f"{sys.executable} -m pytest -q", "cwd": wd})
    assert again["status"] == "success", again

    ok, evidence = verify_bug(wd, {})
    assert ok, evidence
    print(f"PASS: substrate completes fix-a-bug ({evidence})")


def test_substrate_can_diagnose_and_fix_a_build():
    from tests.benchmark_runtime import setup_broken_build, verify_broken_build

    rt = _rt()
    wd = tempfile.mkdtemp()
    setup_broken_build(wd)

    run = rt._execute_tool("run_command", {"command": "sh build.sh", "cwd": wd})
    assert run["status"] == "command_failed"
    assert "json" in (run["stderr"] + run["stdout"]).lower(), run

    rt._execute_tool("edit_file", {
        "path": f"{wd}/config.json",
        "old_text": '"port": 8080,}',
        "new_text": '"port": 8080}',
    })

    again = rt._execute_tool("run_command", {"command": "sh build.sh", "cwd": wd})
    assert again["status"] == "success"
    assert "BUILD_OK" in again["stdout"]

    ok, evidence = verify_broken_build(wd, {})
    assert ok, evidence
    print(f"PASS: substrate completes diagnose-a-build ({evidence})")


def test_substrate_can_rename_across_multiple_files():
    from tests.benchmark_runtime import setup_rename, verify_rename

    rt = _rt()
    wd = tempfile.mkdtemp()
    setup_rename(wd)

    found = rt._execute_tool("search_code", {"query": "get_conn", "path": wd})
    assert found["match_count"] >= 3, found
    assert "db.py:" in found["result"]

    for name in ("db.py", "api.py", "worker.py"):
        r = rt._execute_tool("edit_file", {
            "path": f"{wd}/{name}",
            "old_text": "get_conn",
            "new_text": "open_connection",
            "expect_count": (wd and open(f"{wd}/{name}").read().count("get_conn")),
        })
        assert r["status"] == "success", r

    after = rt._execute_tool("search_code", {"query": "get_conn", "path": wd})
    assert after["match_count"] == 0, "verification should show no stale references remain"

    ok, evidence = verify_rename(wd, {})
    assert ok, evidence
    print(f"PASS: substrate completes multi-file rename ({evidence})")


def test_substrate_can_start_and_verify_a_server():
    from tests.benchmark_runtime import setup_server, verify_server, cleanup_server
    from tools.terminal import actions

    rt = _rt()
    wd = tempfile.mkdtemp()
    setup_server(wd)

    try:
        started = rt._execute_tool("run_background", {
            "command": f"{sys.executable} serve.py", "cwd": wd,
        })
        assert started["status"] == "success", started
        pid = started["pid"]

        listed = rt._execute_tool("list_processes", {})
        assert any(p["pid"] == pid and p["running"] for p in listed["processes"])

        out = rt._execute_tool("process_output", {"pid": pid})
        assert "serving on" in out["output"], out

        ok, evidence = verify_server(wd, {})
        assert ok, evidence
        print(f"PASS: substrate completes start-and-verify-a-server ({evidence})")
    finally:
        cleanup_server(wd, {})


def test_substrate_can_recover_from_a_broken_command():
    from tests.benchmark_runtime import verify_recovery

    rt = _rt()
    wd = tempfile.mkdtemp()

    broken = rt._execute_tool("run_command", {
        "command": "cat missing_file.txt > output.txt", "cwd": wd,
    })
    assert broken["status"] == "command_failed"
    # The diagnosis must be present in the output, not swallowed.
    assert "missing_file" in broken["stderr"], broken

    fixed = rt._execute_tool("run_command", {
        "command": "echo recovered > output.txt", "cwd": wd,
    })
    assert fixed["status"] == "success"

    ok, evidence = verify_recovery(wd, {})
    assert ok, evidence
    print(f"PASS: substrate completes recover-from-broken-command ({evidence})")


def test_substrate_can_inspect_an_unfamiliar_repo():
    from tests.benchmark_runtime import setup_repo

    rt = _rt()
    wd = tempfile.mkdtemp()
    setup_repo(wd)

    o = rt._execute_tool("project_overview", {"path": wd})
    assert o["status"] == "success"
    # Every fact needed to answer the benchmark question is present in one call.
    assert o["package"]["name"] == "inventory-api"
    assert "express" in o["package"]["dependencies"]
    assert o["package"]["scripts"]["test"] == "jest"
    assert o["git"]["is_repo"] is True
    assert o["git"]["recent_commits"], "commit history should be visible"
    print("PASS: substrate supplies every fact needed to explain an unfamiliar repo")


def test_substrate_supports_create_then_modify_without_data_loss():
    from tests.benchmark_runtime import verify_create_modify

    rt = _rt()
    wd = tempfile.mkdtemp()

    rt._execute_tool("write_file", {"path": f"{wd}/notes.txt", "content": "first line\n"})
    r = rt._execute_tool("edit_file", {
        "path": f"{wd}/notes.txt",
        "old_text": "first line\n",
        "new_text": "first line\nsecond line\n",
    })
    assert r["status"] == "success"

    ok, evidence = verify_create_modify(wd, {})
    assert ok, evidence
    print(f"PASS: substrate completes create-then-modify ({evidence})")


def test_missing_path_error_names_what_is_actually_there():
    """Environmental context in an error is what makes it recoverable."""
    rt = _rt()
    wd = tempfile.mkdtemp()
    os.makedirs(f"{wd}/receipts", exist_ok=True)
    for name in ("jan.txt", "feb.txt"):
        open(f"{wd}/receipts/{name}", "w").write("x")

    r = rt._execute_tool("read_file", {"path": f"{wd}/receipts/march.txt"})
    assert r["status"] == "error"
    assert "jan.txt" in r["error"] and "feb.txt" in r["error"], (
        f"a not-found error should say what the directory does contain, got: {r['error']}"
    )
    print("PASS: a missing-path error reports what the directory actually contains")


if __name__ == "__main__":
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        fn()
    print("\nAll substrate capability tests passed.")
