"""Tests for the Computer + Project Runtime V1 capabilities.

These go through CoreRuntime._execute_tool — the same path the model's tool
calls take — rather than calling the tool modules directly, so what is
asserted is what the model would actually receive.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401 — must run before any brain/config import


def _runtime():
    from brain.core_runtime import CoreRuntime
    return CoreRuntime()


# ══ Terminal ═══════════════════════════════════════════════

def test_failing_command_returns_its_output_not_just_an_error():
    """The regression that motivated this milestone: a failing test run used
    to return exactly {'status': 'error', 'error': 'Command failed.'} — the
    pytest output naming the failure went to stdout and was discarded with
    the exception, leaving the model nothing to act on."""
    rt = _runtime()
    r = rt._execute_tool("run_command", {
        "command": "echo 'FAILED test_math.py::test_add - assert 3 == 4'; exit 1"
    })

    assert r["status"] == "command_failed"
    assert r["exit_code"] == 1
    assert "test_math.py::test_add" in r["stdout"], "the failure output must reach the model"
    assert "assert 3 == 4" in r["stdout"]
    print("PASS: a failing command returns exit code and full output")


def test_stderr_survives_a_successful_command():
    """Build tools routinely write warnings to stderr while exiting 0. That
    output used to be dropped entirely."""
    rt = _runtime()
    r = rt._execute_tool("run_command", {"command": "echo out; echo warn 1>&2"})

    assert r["status"] == "success"
    assert "out" in r["stdout"]
    assert "warn" in r["stderr"], "stderr must not be lost on success"
    print("PASS: stderr survives a successful command")


def test_command_reports_cwd_and_respects_it():
    rt = _runtime()
    tmp = tempfile.mkdtemp()
    r = rt._execute_tool("run_command", {"command": "pwd", "cwd": tmp})

    assert r["status"] == "success"
    assert r["cwd"] == tmp
    assert os.path.realpath(r["stdout"].strip()) == os.path.realpath(tmp)
    print("PASS: commands run in, and report, the requested directory")


def test_timeout_returns_partial_output_rather_than_nothing():
    rt = _runtime()
    r = rt._execute_tool("run_command", {
        "command": "echo before-the-hang; sleep 30",
        "timeout": 2,
    })

    assert r["status"] == "error"
    assert r["timed_out"] is True
    assert "before-the-hang" in r["stdout"], "partial output is the diagnosis for a hang"
    print("PASS: a timeout still returns what the command managed to print")


# ══ Background processes ═══════════════════════════════════

def test_background_process_can_be_listed_read_and_killed():
    """Starting a server used to be fire-and-forget: a pid and nothing else,
    so 'is it actually up?' was unanswerable."""
    rt = _runtime()
    started = rt._execute_tool("run_background", {
        "command": "for i in 1 2 3 4 5 6 7 8 9 10; do echo tick-$i; sleep 1; done"
    })
    assert started["status"] == "success", started
    pid = started["pid"]

    listing = rt._execute_tool("list_processes", {})
    mine = [p for p in listing["processes"] if p["pid"] == pid]
    assert mine and mine[0]["running"] is True

    out = rt._execute_tool("process_output", {"pid": pid})
    assert out["status"] == "success"
    assert "tick-" in out["output"], "must be able to read what a server printed"

    killed = rt._execute_tool("kill_process", {"pid": pid})
    assert killed["status"] == "success"

    after = rt._execute_tool("list_processes", {})
    mine_after = [p for p in after["processes"] if p["pid"] == pid]
    assert mine_after and mine_after[0]["running"] is False
    print("PASS: background processes can be listed, read, and stopped")


def test_background_process_that_dies_immediately_is_reported_as_failed():
    rt = _runtime()
    r = rt._execute_tool("run_background", {
        "command": "echo cannot-bind-port-already-in-use 1>&2; exit 1"
    })
    assert r["status"] == "error"
    assert r["running"] is False
    assert "cannot-bind-port" in r["output"]
    print("PASS: a background process that fails to start says why")


def test_unknown_pid_is_refused_rather_than_killing_something_else():
    rt = _runtime()
    r = rt._execute_tool("kill_process", {"pid": 999999})
    assert r["status"] == "error"
    assert "999999" in r["error"]
    print("PASS: kill_process only touches processes Mike started")


# ══ Editing ════════════════════════════════════════════════

def test_edit_file_replaces_exactly_and_returns_a_diff():
    rt = _runtime()
    tmp = tempfile.mkdtemp()
    target = Path(tmp) / "app.py"
    target.write_text("def add(a, b):\n    return a - b\n")

    r = rt._execute_tool("edit_file", {
        "path": str(target),
        "old_text": "return a - b",
        "new_text": "return a + b",
    })

    assert r["status"] == "success", r
    assert r["replacements"] == 1
    assert target.read_text() == "def add(a, b):\n    return a + b\n"
    assert "-    return a - b" in r["diff"]
    assert "+    return a + b" in r["diff"]
    print("PASS: edit_file makes an exact change and shows the diff")


def test_edit_refuses_ambiguous_match_and_changes_nothing():
    """Silently editing the first of several identical snippets is how an
    edit 'succeeds' and corrupts a file."""
    rt = _runtime()
    tmp = tempfile.mkdtemp()
    target = Path(tmp) / "dup.py"
    original = "x = 1\ny = 1\nz = 1\n"
    target.write_text(original)

    r = rt._execute_tool("edit_file", {
        "path": str(target), "old_text": "= 1", "new_text": "= 2",
    })

    assert r["status"] == "error"
    assert r["reason"] == "ambiguous"
    assert r["occurrences"] == 3
    assert target.read_text() == original, "an ambiguous edit must change nothing"
    print("PASS: an ambiguous edit is refused and the file is untouched")


def test_edit_that_does_not_match_changes_nothing():
    rt = _runtime()
    tmp = tempfile.mkdtemp()
    target = Path(tmp) / "a.py"
    target.write_text("hello\n")

    r = rt._execute_tool("edit_file", {
        "path": str(target), "old_text": "not-present", "new_text": "x",
    })
    assert r["status"] == "error"
    assert r["reason"] == "not_found"
    assert target.read_text() == "hello\n"
    print("PASS: a non-matching edit is refused and the file is untouched")


def test_multi_edit_is_all_or_nothing():
    rt = _runtime()
    tmp = tempfile.mkdtemp()
    target = Path(tmp) / "cfg.py"
    original = "HOST = 'localhost'\nPORT = 8000\nDEBUG = True\n"
    target.write_text(original)

    # Second edit is fine, third cannot match — nothing should be written.
    r = rt._execute_tool("multi_edit", {
        "path": str(target),
        "edits": [
            {"old_text": "PORT = 8000", "new_text": "PORT = 9000"},
            {"old_text": "DEBUG = True", "new_text": "DEBUG = False"},
            {"old_text": "MISSING = 1", "new_text": "MISSING = 2"},
        ],
    })

    assert r["status"] == "error"
    assert r["failed_edit"] == 3
    assert target.read_text() == original, "a partial multi_edit would leave a broken file"

    # And the same set without the bad edit applies cleanly.
    ok = rt._execute_tool("multi_edit", {
        "path": str(target),
        "edits": [
            {"old_text": "PORT = 8000", "new_text": "PORT = 9000"},
            {"old_text": "DEBUG = True", "new_text": "DEBUG = False"},
        ],
    })
    assert ok["status"] == "success"
    assert "PORT = 9000" in target.read_text()
    assert "DEBUG = False" in target.read_text()
    print("PASS: multi_edit applies all edits or none")


def test_edits_are_revertible_like_any_other_change():
    """A targeted edit must inherit the same undo guarantee as write_file."""
    from brain import revert_store

    rt = _runtime()
    tmp = tempfile.mkdtemp()
    target = Path(tmp) / "r.py"
    target.write_text("value = 1\n")

    rt._execute_tool("edit_file", {
        "path": str(target), "old_text": "value = 1", "new_text": "value = 99",
    })
    assert target.read_text() == "value = 99\n"

    snap = revert_store._db().execute(
        "SELECT * FROM snapshots ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    assert snap is not None
    result = revert_store.revert(snap["id"])
    assert result["status"] == "success"
    assert target.read_text() == "value = 1\n"
    print("PASS: targeted edits are snapshotted and revertible")


def test_read_lines_gives_numbered_addressable_output():
    rt = _runtime()
    tmp = tempfile.mkdtemp()
    target = Path(tmp) / "many.py"
    target.write_text("\n".join(f"line{i}" for i in range(1, 51)) + "\n")

    r = rt._execute_tool("read_lines", {"path": str(target), "offset": 10, "limit": 5})
    assert r["status"] == "success"
    assert r["total_lines"] == 50
    assert r["shown"] == "10-14"
    assert "10\tline10" in r["content"]
    assert "line20" not in r["content"]
    print("PASS: read_lines returns numbered, addressable slices")


# ══ Project inspection ═════════════════════════════════════

def test_project_overview_detects_type_git_state_and_recent_work():
    rt = _runtime()
    tmp = tempfile.mkdtemp()
    root = Path(tmp)
    (root / "package.json").write_text(
        '{"name": "demo", "version": "1.0.0", '
        '"scripts": {"test": "jest", "dev": "vite"}, '
        '"dependencies": {"react": "^18.0.0"}}'
    )
    (root / "index.js").write_text("console.log('hi')\n")

    subprocess.run(["git", "init", "-q"], cwd=tmp, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "initial"],
        cwd=tmp, capture_output=True,
    )
    (root / "dirty.js").write_text("// uncommitted\n")

    r = rt._execute_tool("project_overview", {"path": tmp})

    assert r["status"] == "success"
    assert "Node/JavaScript" in r["project_types"]
    assert r["package"]["scripts"]["test"] == "jest"
    assert "react" in r["package"]["dependencies"]
    assert r["git"]["is_repo"] is True
    assert r["git"]["dirty"] is True
    assert any("dirty.js" in c for c in r["git"]["changed_files"])
    assert any(f["path"] == "dirty.js" for f in r["recently_modified"])
    print("PASS: project_overview reports type, scripts, git state, recent work")


def test_project_tree_filters_noise():
    rt = _runtime()
    tmp = tempfile.mkdtemp()
    root = Path(tmp)
    (root / "src").mkdir()
    (root / "src" / "main.py").write_text("x")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "junk.js").write_text("x")

    r = rt._execute_tool("project_tree", {"path": tmp})
    assert r["status"] == "success"
    assert "main.py" in r["tree"]
    assert "junk.js" not in r["tree"], "node_modules must not crowd out real files"
    assert "node_modules" in r["skipped_directories"]
    print("PASS: project_tree filters noise and says what it skipped")


def test_search_code_returns_line_numbers():
    rt = _runtime()
    tmp = tempfile.mkdtemp()
    (Path(tmp) / "svc.py").write_text(
        "import os\n\n\ndef connect_db():\n    return 'db'\n"
    )

    r = rt._execute_tool("search_code", {"query": "connect_db", "path": tmp})
    assert r["status"] == "success"
    assert r["match_count"] >= 1
    assert "svc.py:4:" in r["result"], f"expected file:line:text, got {r['result']!r}"
    print("PASS: search_code returns file:line:text")


def test_search_code_reports_no_matches_as_success_not_failure():
    """Finding nothing is a real answer, not an error to recover from."""
    rt = _runtime()
    tmp = tempfile.mkdtemp()
    (Path(tmp) / "x.py").write_text("nothing here\n")

    r = rt._execute_tool("search_code", {"query": "zzz_not_present", "path": tmp})
    assert r["status"] == "success"
    assert r["match_count"] == 0
    print("PASS: an empty search result is a successful observation")


# ══ Safety ═════════════════════════════════════════════════

def test_new_mutating_tools_are_behind_the_existing_confirmation_gate():
    """The safety guarantee must extend to the new capabilities, through the
    same single gate — not a second, parallel one."""
    from brain.core_tools import needs_confirmation

    for name in ("edit_file", "multi_edit", "kill_process"):
        assert needs_confirmation(name, {}), f"{name} must require confirmation"

    for name in ("read_lines", "project_overview", "project_tree",
                 "search_code", "list_processes", "process_output"):
        assert not needs_confirmation(name, {}), f"{name} is read-only, should not gate"

    print("PASS: new mutating tools are gated, read-only ones are not")


def test_unknown_parameter_is_refused_rather_than_silently_dropped():
    """Regression from the Qwen3.5 9B brain swap.

    A model called run_command with `path` (meaning the working directory)
    instead of `cwd`. Every required parameter was present, so the call ran —
    with `path` silently discarded and cwd falling back to os.getcwd(), which
    is Mike's own source tree. It really did write the user's notes.txt and
    output.txt into the repository. Running a command somewhere other than
    where it was asked for is worse than refusing, so an unrecognised
    parameter now fails the call and names the right one.
    """
    from brain.core_tools import check_arguments

    problem = check_arguments("run_command", {"path": "/tmp/x", "command": "ls"})
    assert problem is not None, "an unknown parameter must not be silently ignored"
    assert "does not take path" in problem
    assert "cwd" in problem, "the message should name the parameter that was meant"

    # And it must not over-reject legitimate calls.
    assert check_arguments("run_command", {"command": "ls", "cwd": "/tmp"}) is None
    assert check_arguments("run_command", {"command": "ls"}) is None
    print("PASS: unknown parameters are refused, valid calls still pass")


def test_runtime_uses_the_model_named_in_config():
    """The brain model must come from config, not a second hardcoded copy.

    core_runtime.py used to declare its own OLLAMA_MODEL = "qwen3:8b", so
    brain/diagnostics.py could check OLLAMA_CHAT_MODEL and report a model as
    available that the runtime never actually ran.
    """
    import brain.core_runtime as cr
    from config.ollama import OLLAMA_CHAT_MODEL, OLLAMA_SUMMARY_MODEL, OLLAMA_VISION_MODEL

    assert cr.OLLAMA_MODEL == OLLAMA_CHAT_MODEL, (
        "the runtime's brain model must be the one config declares"
    )
    # qwen3.5:2b was retired and removed from Ollama; nothing may still ask
    # for it. The brain is qwen3.5:9b. An earlier note here recorded that the
    # Qwen3.5 9B trial "failed tool calling" and that qwen3:8b was therefore
    # still the brain; both halves were wrong. The tool-call failures were
    # Mike truncating its own tool schemas under a 4,096-token budget and
    # inheriting the model's presence_penalty of 1.5 -- 58% failure with the
    # penalty, 0% without it.
    for name in (OLLAMA_CHAT_MODEL, OLLAMA_VISION_MODEL, OLLAMA_SUMMARY_MODEL):
        assert "qwen3.5:2b" not in name, f"a removed model is still referenced: {name}"
    print(f"PASS: brain={OLLAMA_CHAT_MODEL} vision={OLLAMA_VISION_MODEL} (no removed models referenced)")


def test_every_new_tool_is_declared_to_the_model():
    """A tool the runtime can execute but never declares is invisible — the
    exact infrastructure-vs-feature gap found in the product audit."""
    from brain.core_runtime import _DIRECT_TOOLS
    from brain.core_tools import OLLAMA_TOOLS

    declared = {t["function"]["name"] for t in OLLAMA_TOOLS}
    missing = _DIRECT_TOOLS - declared
    assert not missing, f"executable but never declared to the model: {missing}"
    print(f"PASS: all {len(_DIRECT_TOOLS)} runtime tools are declared to the model")




def test_mike_prompt_fits_the_context_without_truncation():
    """Regression for a silent, long-standing bug found while diagnosing the
    Qwen3.5 9B tool-call failures.

    Mike's system prompt plus its 30 tool schemas render to ~4,950 tokens.
    Ollama only accepts roughly half of num_ctx as input, so with the old
    num_ctx=4096 the effective input limit was 2,050 and every single request
    was truncated — the server log shows "truncating input prompt limit=2050
    prompt=4956" on every call. The model was being given tool definitions cut
    in half, which is why it invented argument names (`text` for `content`,
    `directory` for `cwd`) and why qwen3.5's stricter parser rejected the
    output outright with an XML error.

    This asserts the budget directly rather than the symptom, so shrinking the
    context or growing the prompt fails here instead of silently degrading
    every tool call.
    """
    import json

    from brain.core_runtime import SYSTEM_PROMPT
    from config.ollama import NUM_CTX          # the value that reaches Ollama
    from brain.core_tools import OLLAMA_TOOLS

    rendered = SYSTEM_PROMPT + json.dumps(OLLAMA_TOOLS)
    approx_tokens = len(rendered) / 4          # ~4 chars/token, close enough

    # Measured, not derived: Ollama reported prompt_eval_count=4956 for this
    # prompt and truncated it to 2050 at num_ctx=4096. It stops truncating
    # once num_ctx exceeds the prompt with headroom for the reply, which is
    # what this asserts. (Ollama can further halve the per-request budget when
    # it serves multiple slots, so the headroom here is deliberate rather than
    # tight.)
    budget = NUM_CTX - 300                     # num_predict reserved for the reply

    assert approx_tokens < budget, (
        f"Mike's prompt is ~{approx_tokens:.0f} tokens but only ~{budget} are "
        f"available at num_ctx={NUM_CTX}. It would be truncated, and truncated "
        "tool schemas produce malformed tool calls."
    )
    print(
        f"PASS: prompt ~{approx_tokens:.0f} tok fits within num_ctx={NUM_CTX} "
        f"(budget ~{budget})"
    )




# ══ Verification primitives (Runtime V2) ═══════════════════

def test_a_successful_edit_can_still_leave_broken_code():
    """The distinction the runtime exists to expose: `edit_file` reports
    success because the text was replaced, which says nothing about whether
    the result still parses. check_syntax is what turns 'the write worked'
    into 'the change is valid'."""
    rt = _runtime()
    tmp = tempfile.mkdtemp()
    target = Path(tmp) / "calc.py"
    target.write_text("def add(a, b):\n    return a + b\n")

    edit = rt._execute_tool("edit_file", {
        "path": str(target), "old_text": "return a + b", "new_text": "return a +",
    })
    assert edit["status"] == "success", "the write itself genuinely succeeded"

    check = rt._execute_tool("check_syntax", {"path": str(target)})
    assert check["valid"] is False, "a broken file must be reported as broken"
    assert check["line"] == 2
    print("PASS: a successful write is distinguished from a valid change")


def test_check_syntax_validates_python_and_json_and_admits_what_it_cannot_do():
    rt = _runtime()
    tmp = tempfile.mkdtemp()

    good = Path(tmp) / "ok.py"
    good.write_text("x = 1\n")
    assert rt._execute_tool("check_syntax", {"path": str(good)})["valid"] is True

    bad_json = Path(tmp) / "bad.json"
    bad_json.write_text('{"a": 1,}')
    result = rt._execute_tool("check_syntax", {"path": str(bad_json)})
    assert result["valid"] is False and result["language"] == "json"

    # An honest "I can't check this" beats a confident wrong answer.
    unknown = Path(tmp) / "notes.rs"
    unknown.write_text("fn main() {}\n")
    unchecked = rt._execute_tool("check_syntax", {"path": str(unknown)})
    assert unchecked["valid"] is None
    assert "can't syntax-check" in unchecked["result"]
    print("PASS: syntax checking is honest about its own limits")


def test_server_lifecycle_produces_evidence_at_every_step():
    """start -> confirm listening -> confirm serving -> stop -> confirm gone.
    Without this, 'I started the server' is an unverifiable claim."""
    import time

    rt = _runtime()
    tmp = tempfile.mkdtemp()
    port = 8793
    Path(tmp, "serve.py").write_text(
        "import http.server,socketserver\n"
        "class H(http.server.SimpleHTTPRequestHandler):\n"
        "    def do_GET(self):\n"
        "        self.send_response(200); self.end_headers()\n"
        "        self.wfile.write(b'<h1>Ember</h1>')\n"
        f"with socketserver.TCPServer(('',{port}),H) as s:\n"
        "    print('serving',flush=True); s.serve_forever()\n"
    )

    assert rt._execute_tool("check_port", {"port": port})["listening"] is False

    started = rt._execute_tool("run_background", {
        "command": f"{sys.executable} serve.py", "cwd": tmp,
    })
    assert started["status"] == "success"
    try:
        time.sleep(1.5)
        assert rt._execute_tool("check_port", {"port": port})["listening"] is True

        served = rt._execute_tool("check_url", {
            "url": f"http://127.0.0.1:{port}", "expect": "Ember",
        })
        assert served["http_status"] == 200
        assert served["expected_present"] is True
    finally:
        rt._execute_tool("kill_process", {"pid": started["pid"]})
        time.sleep(0.5)

    assert rt._execute_tool("check_port", {"port": port})["listening"] is False
    print("PASS: the whole server lifecycle is verifiable")


def test_unreachable_url_explains_whether_anything_is_listening():
    """'Connection refused' and 'listening but not serving this path' need
    completely different next steps, so they are reported differently."""
    rt = _runtime()
    result = rt._execute_tool("check_url", {"url": "http://127.0.0.1:9998"})
    assert result["status"] == "error"
    assert result["reachable"] is False
    assert result["port_listening"] is False
    assert "Nothing is listening" in result["error"]
    print("PASS: an unreachable URL says why, not just that it failed")


def test_search_code_recovers_from_regex_escaped_queries():
    """Most code-search tools take patterns, so a model reasonably escapes
    regex metacharacters. This one matches literally by default, which makes
    such a query unmatchable -- the backslashes are searched for too.

    Measured on the bottle repository task: five consecutive dead searches
    for `self.builder\\[rule\\] = builder`, a quarter of that run's step
    budget, while the unescaped query matched on the first try. The tool now
    retries without the escapes and reports that it did."""
    import tempfile

    tmp = tempfile.mkdtemp()
    Path(tmp, "router.py").write_text("self.builder[rule] = builder\n")

    rt = _runtime()
    escaped = rt._execute_tool(
        "search_code", {"query": r"self.builder\[rule\] = builder", "path": tmp}
    )
    assert escaped["match_count"] == 1, "an escaped query must still find the line"
    assert "note" in escaped, "the recovery must be reported, not silent"

    plain = rt._execute_tool(
        "search_code", {"query": "self.builder[rule] = builder", "path": tmp}
    )
    assert plain["match_count"] == 1
    assert "note" not in plain, "an unescaped query needs no explanation"
    print("PASS: a regex-escaped query recovers instead of dead-ending")


def test_search_code_explains_literal_matching_when_nothing_is_found():
    """A bare 'no matches' gives nothing to correct. The failure that costs
    steps is not knowing *why* the query missed."""
    import tempfile

    rt = _runtime()
    result = rt._execute_tool(
        "search_code", {"query": "definitely_absent_xyz", "path": tempfile.mkdtemp()}
    )
    assert result["match_count"] == 0
    assert result["status"] == "success"
    assert "literal" in result["result"].lower(), "say how the query was matched"
    assert "regex" in result["result"].lower(), "name the way to change it"
    print("PASS: a no-match result explains how the query was interpreted")


def test_search_code_still_honours_an_explicit_regex_request():
    """The recovery must not quietly turn every query into a literal one."""
    import tempfile

    tmp = tempfile.mkdtemp()
    Path(tmp, "a.py").write_text("def add(self, rule, method):\n")

    rt = _runtime()
    result = rt._execute_tool(
        "search_code", {"query": r"def add\(.*rule", "path": tmp, "regex": True}
    )
    assert result["match_count"] == 1, "regex=True must still search as a pattern"
    print("PASS: an explicit regex search is unaffected")


def test_verification_tools_are_read_only_and_ungated():
    from brain.core_tools import needs_confirmation

    for name in ("check_url", "check_port", "check_syntax"):
        assert not needs_confirmation(name, {}), f"{name} observes and must not gate"
    print("PASS: verification tools are read-only")


if __name__ == "__main__":
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        fn()
    print("\nAll runtime V1 tests passed.")
