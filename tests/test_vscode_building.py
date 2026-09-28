"""Building projects with the student in VS Code.

Mike opens what he makes where the student works, runs a dev server in a
terminal there they can watch and stop, knows what their own terminal said
when something failed, and gets VS Code's own checkers' word on every file he
writes into a project it has open. Everything here runs against fakes; the
real extension is exercised against a real VS Code by the e2e probe.
"""
from __future__ import annotations

import os
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import _isolate  # noqa: F401,E402

import ide.bridge as bridge_module  # noqa: E402
from hostplatform import processes  # noqa: E402
from ide import manager  # noqa: E402
from ide.bridge import IDEBridge  # noqa: E402
from ide.contracts import IDEContext, TerminalRun  # noqa: E402
from ide.vscode_adapter import VSCodeAdapter  # noqa: E402
from tools.filesystem import edits  # noqa: E402
from tools.terminal import actions  # noqa: E402


# ── commands reach bash, wherever Git put it ─────────────────────────────

def _no_install_dirs(monkeypatch):
    for var in ("ProgramW6432", "ProgramFiles", "LOCALAPPDATA"):
        monkeypatch.delenv(var, raising=False)


def test_git_bash_is_found_beside_git_when_bash_is_not_on_path(tmp_path, monkeypatch):
    git_root = tmp_path / "Git"
    (git_root / "cmd").mkdir(parents=True)
    (git_root / "bin").mkdir()
    (git_root / "cmd" / "git.exe").write_text("")
    (git_root / "bin" / "bash.exe").write_text("")
    found = {"bash": None, "git": str(git_root / "cmd" / "git.exe")}
    monkeypatch.setattr(processes.shutil, "which", lambda name: found.get(name))
    _no_install_dirs(monkeypatch)
    assert processes._find_git_bash() == str(git_root / "bin" / "bash.exe")


def test_the_wsl_launcher_is_never_taken_for_git_bash(tmp_path, monkeypatch):
    system = tmp_path / "Windows"
    (system / "System32").mkdir(parents=True)
    (system / "System32" / "bash.exe").write_text("")
    monkeypatch.setenv("SystemRoot", str(system))
    monkeypatch.setattr(processes.shutil, "which",
                        lambda name: str(system / "System32" / "bash.exe") if name == "bash" else None)
    _no_install_dirs(monkeypatch)
    assert processes._find_git_bash() is None


# ── the bridge: a command for one window goes to that window ─────────────

def _window(bridge, window_id, focused):
    bridge._store_context({"windowId": window_id, "focused": focused,
                           "workspace": {"root": f"C:\\{window_id}", "folders": [f"C:\\{window_id}"]}})


def test_a_command_for_one_window_is_not_handed_to_another(monkeypatch):
    bridge = IDEBridge(port=0)
    _window(bridge, "a", focused=False)
    _window(bridge, "b", focused=True)
    answers = {}
    sender = threading.Thread(target=lambda: answers.update(
        r=bridge.send_command("runOutput", {"runId": "r1"}, timeout=3, window_id="a")))
    sender.start()
    time.sleep(0.1)
    monkeypatch.setattr(bridge_module, "POLL_HOLD_SECONDS", 0.2)
    assert bridge._await_command("b") is None, "the focused window must not take window a's command"
    command = bridge._await_command("a")
    assert command and command["action"] == "runOutput"
    bridge._store_result({"id": command["id"], "result": {"ok": True, "running": True}})
    sender.join(3)
    assert answers["r"] == {"ok": True, "running": True}


def test_a_command_nobody_picked_up_is_not_carried_out_later():
    bridge = IDEBridge(port=0)
    _window(bridge, "gone", focused=True)
    assert bridge.send_command("openFile", {"path": "x"}, timeout=0.2)["ok"] is False
    assert bridge._pending == []


# ── what the terminal said ────────────────────────────────────────────────

def _run(**kw):
    base = dict(terminal="bash", command="npm run build", running=False, exit_code=1,
                output="\n".join(f"line {i}" for i in range(40)) + "\nError: Cannot find module 'vite'",
                ended_at=time.time() - 30)
    base.update(kw)
    return TerminalRun(**base)


def test_a_fresh_failure_in_their_terminal_comes_with_each_turn():
    ctx = IDEContext(editor="VS Code", workspace_root="C:\\p", terminal=[_run()])
    said = ctx.describe()
    assert "npm run build" in said and "exited with code 1" in said
    assert "Cannot find module 'vite'" in said, "the error, at the end of the output, is shown"
    assert "line 5\n" not in said, "each turn carries only the end of it"


def test_an_old_or_successful_command_is_not_repeated_every_turn():
    old = IDEContext(workspace_root="C:\\p", terminal=[_run(ended_at=time.time() - 3600)])
    fine = IDEContext(workspace_root="C:\\p", terminal=[_run(exit_code=0)])
    assert "npm run build" not in old.describe()
    assert "npm run build" not in fine.describe()


def test_what_is_running_is_said_and_asking_shows_everything():
    ctx = IDEContext(workspace_root="C:\\p", terminal=[
        _run(exit_code=0, command="npm install"),
        _run(command="npm run dev", running=True, exit_code=None, by_mike=True, output="ready on :5173")])
    assert "`npm run dev` (Mike started it)" in ctx.describe()
    full = ctx.describe(terminal="full")
    assert "npm install" in full and "ready on :5173" in full


def test_the_project_and_each_command_say_where_they_are():
    """Without the folder, the model guessed relative paths for the
    project's files (three wasted steps in a real run)."""
    ctx = IDEContext(editor="VS Code", workspace_name="quiz", workspace_root="C:\\work\\quiz",
                     terminal=[_run(command="node quiz.js", cwd="C:\\work\\quiz")])
    said = ctx.describe()
    assert "“quiz” (C:\\work\\quiz)" in said
    assert "`node quiz.js` in C:\\work\\quiz" in said


def test_a_command_folder_is_read_like_any_other_path(tmp_path, monkeypatch):
    import brain.core_runtime as cr
    from tools.filesystem import path_utils
    (tmp_path / "proj").mkdir()
    monkeypatch.setattr(path_utils, "HOME", tmp_path)
    assert cr._command_folder("proj") == str(tmp_path / "proj"), "relative to home, as files are"
    assert cr._command_folder(str(tmp_path / "proj")) == str(tmp_path / "proj")
    missing = cr._command_folder("nope")
    assert missing["status"] == "error" and "nope" in missing["error"] and "Nothing was run" in missing["error"]


def test_the_extension_snapshot_becomes_terminal_runs():
    bridge = IDEBridge(port=0)
    bridge._store_context({"windowId": "w", "focused": True, "canRunCommands": True,
                           "workspace": {"name": "p", "root": "C:\\p", "folders": ["C:\\p"]},
                           "terminal": [{"id": "r1", "terminal": "bash", "command": "pytest",
                                         "running": False, "exitCode": 2, "output": "1 failed",
                                         "byMike": False, "startedAt": 1.0, "endedAt": 2.0}]})
    ctx = VSCodeAdapter(bridge).get_context()
    assert ctx.can_run_commands and ctx.window_id == "w" and ctx.workspace_folders == ["C:\\p"]
    assert ctx.terminal[0].command == "pytest" and ctx.terminal[0].exit_code == 2
    assert ctx.terminal[0].failed


# ── a server Mike starts runs where they can see it ───────────────────────

@pytest.fixture
def fake_editor_terminal(monkeypatch):
    state = {"running": True, "stopped": False, "asked": []}

    def run_in_terminal(command, cwd, wait=4.0):
        state["asked"].append((command, cwd))
        return {"ok": True, "id": "r7", "pid": 4242, "window": "w1", "terminal": "Mike: npm run dev",
                "running": True, "exitCode": None, "output": "VITE ready on http://localhost:5173"}

    def run_output(window, run_id):
        assert (window, run_id) == ("w1", "r7")
        return {"ok": True, "running": state["running"], "exitCode": None if state["running"] else 130,
                "output": "VITE ready on http://localhost:5173\nGET /"}

    def stop_run(window, run_id):
        state["stopped"], state["running"] = True, False
        return {"ok": True, "running": False, "exitCode": 130, "output": "^C"}

    monkeypatch.setattr(manager, "run_in_terminal", run_in_terminal)
    monkeypatch.setattr(manager, "run_output", run_output)
    monkeypatch.setattr(manager, "stop_run", stop_run)
    yield state
    with actions._processes_lock:
        actions._processes.pop(4242, None)


def test_a_dev_server_runs_in_their_vs_code_terminal(fake_editor_terminal, tmp_path):
    result = actions.run_background("npm run dev", cwd=str(tmp_path))
    assert result["running"] and result["pid"] == 4242
    assert "VS Code" in result["where"] and "Mike: npm run dev" in result["where"]
    assert fake_editor_terminal["asked"] == [("npm run dev", str(tmp_path))]
    listed = actions.list_processes()["processes"]
    assert any(p["pid"] == 4242 and p["running"] for p in listed)
    assert "GET /" in actions.process_output(4242)["output"]


def test_stopping_it_stops_it_there(fake_editor_terminal, tmp_path):
    actions.run_background("npm run dev", cwd=str(tmp_path))
    result = actions.kill_process(4242)
    assert fake_editor_terminal["stopped"] and "VS Code" in result["result"]


def test_quitting_mike_leaves_their_terminal_alone(fake_editor_terminal, tmp_path):
    actions.run_background("npm run dev", cwd=str(tmp_path))
    actions.shutdown_all()
    assert not fake_editor_terminal["stopped"], "it's theirs now, in front of them"


def test_with_no_editor_it_runs_out_of_sight_as_before(monkeypatch, tmp_path):
    monkeypatch.setattr(manager, "run_in_terminal", lambda *a, **k: None)
    result = actions.run_background("python -c \"import time; time.sleep(30)\"", cwd=str(tmp_path))
    try:
        assert result["running"] and "where" not in result
    finally:
        actions.kill_process(result["pid"])


@pytest.mark.skipif(sys.platform != "win32", reason="ports are read from Windows' own table")
def test_a_command_that_turns_out_to_be_a_server_is_not_waited_on(tmp_path):
    """A server started as a command that finishes held a task up for the
    whole minute. Listening on a port is the fact that says what it is: it's
    kept running as a background process, and the model told at once."""
    import socket
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    started = time.monotonic()
    result = actions.run(f"python -m http.server {port} --bind 127.0.0.1", cwd=str(tmp_path), timeout=60)
    try:
        assert time.monotonic() - started < 15, "not held for the whole timeout"
        assert result["still_running"] and result["listening_on"] == [port]
        assert any(p["pid"] == result["pid"] and p["running"] for p in actions.list_processes()["processes"])
    finally:
        actions.kill_process(result["pid"])


# ── opening what he made ──────────────────────────────────────────────────

def test_a_project_folder_opens_in_vs_code(tmp_path, monkeypatch):
    started = []
    monkeypatch.setattr(manager, "_start_code", lambda args: started.append(args) or {"ok": True})
    result = manager.open_in_editor(str(tmp_path))
    assert result["ok"] and result["kind"] == "folder"
    assert started == [[str(tmp_path)]]


def test_a_file_opens_in_the_window_that_has_its_project_and_comes_forward(tmp_path, monkeypatch):
    target = tmp_path / "src" / "app.js"
    target.parent.mkdir()
    target.write_text("x")
    other = IDEContext(workspace_name="other", workspace_root="C:\\other", window_id="w0")
    mine = IDEContext(workspace_name=tmp_path.name, workspace_root=str(tmp_path),
                      workspace_folders=[str(tmp_path)], window_id="w1")
    opened, raised = [], []

    class Adapter:
        def context_of(self, raw):
            return raw

        def open_file(self, path, line=None, window=""):
            opened.append((path, line, window))
            return {"ok": True}

    monkeypatch.setattr(manager, "active_adapter", lambda: Adapter())
    monkeypatch.setattr(manager, "is_connected", lambda: True)
    monkeypatch.setattr(manager._bridge, "live_contexts", lambda: [other, mine])
    monkeypatch.setattr(manager, "_raise_window", lambda ctx: raised.append(ctx.window_id))
    result = manager.open_in_editor(str(target), 12)
    assert result["ok"] and opened == [(str(target), 12, "w1")] and raised == ["w1"]


@pytest.mark.skipif(sys.platform != "win32", reason="the Start menu is Windows'")
def test_open_this_in_an_app_hands_it_the_folder_even_from_the_start_menu(monkeypatch, tmp_path):
    from hostplatform import shell

    def not_on_path(*a, **k):
        raise FileNotFoundError(a[0])

    started = []
    monkeypatch.setattr(os, "startfile", not_on_path)
    monkeypatch.setattr(shell, "_start_menu_program", lambda name: r"C:\VS Code\Code.exe")
    monkeypatch.setattr(shell.subprocess, "Popen", lambda argv, **k: started.append(argv))
    assert shell.open_application("Visual Studio Code", str(tmp_path)) is True
    assert started == [[r"C:\VS Code\Code.exe", str(tmp_path)]], "the folder went with it"

    # A Store app has no program to hand it to: it opens, and says the file didn't go.
    started.clear()
    monkeypatch.setattr(shell, "_start_menu_program", lambda name: None)
    monkeypatch.setattr(shell, "_resolve_start_app", lambda name: "Some.App_123!App")
    assert shell.open_application("Some App", str(tmp_path)) is False
    assert started == [["explorer.exe", "shell:AppsFolder\\Some.App_123!App"]]


def test_nothing_there_is_said_plainly(tmp_path):
    result = manager.open_in_editor(str(tmp_path / "missing.py"))
    assert not result["ok"] and "missing.py" in result["error"]


# ── VS Code's own word on the files he writes ─────────────────────────────

def test_files_written_into_an_open_project_come_back_with_vs_codes_problems(tmp_path, monkeypatch):
    asked = []

    def problems_for(paths, wait=2.5):
        asked.append(list(paths))
        return {paths[0]: {"reported": True, "problems": [
                    {"line": 1, "severity": "error", "message": "Type 'string' is not assignable to type 'number'.",
                     "source": "ts"}]},
                paths[1]: {"reported": False, "problems": []}}

    monkeypatch.setattr(manager, "problems_for", problems_for)
    result = edits.write_files([{"path": str(tmp_path / "a.ts"), "content": "const n: number = 'x'\n"},
                                {"path": str(tmp_path / "b.ts"), "content": "export {}\n"}])
    assert asked == [[str(tmp_path / "a.ts"), str(tmp_path / "b.ts")]]
    first, second = result["files"]
    assert "not assignable" in first["problems"]
    assert "problems" not in second, "a file VS Code said nothing about isn't claimed clean"
    assert "b.ts" in result["editor_check"]


def test_an_edit_on_disk_comes_back_with_vs_codes_problems(tmp_path, monkeypatch):
    path = tmp_path / "app.py"
    path.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(manager, "problems_for", lambda paths, wait=2.5: {paths[0]: {
        "reported": True, "problems": [{"line": 1, "severity": "error", "message": "\"y\" is not defined"}]}})
    result = edits.edit_file(str(path), "x = 1", "x = y")
    assert "is not defined" in result["problems"]


def test_only_files_inside_the_open_project_are_checked(tmp_path, monkeypatch):
    sent = []

    class Adapter:
        def problems(self, paths, wait, window=""):
            sent.append(paths)
            return {"ok": True, "files": [{"path": p, "reported": False, "problems": []} for p in paths]}

    project = IDEContext(workspace_root=str(tmp_path / "proj"), workspace_folders=[str(tmp_path / "proj")],
                         window_id="w")
    monkeypatch.setattr(manager, "is_connected", lambda: True)
    monkeypatch.setattr(manager, "active_adapter", lambda: Adapter())
    monkeypatch.setattr(manager, "_window_for", lambda path: project)
    inside, outside = str(tmp_path / "proj" / "a.py"), str(tmp_path / "notes.txt")
    assert manager.problems_for([inside, outside]) == {inside: {"reported": False, "problems": []}}
    assert sent == [[inside]]
    assert manager.problems_for([outside]) is None


def test_check_syntax_adds_what_vs_code_knows(tmp_path, monkeypatch):
    from tools.verify import checks
    path = tmp_path / "page.tsx"
    path.write_text("export const A = () => <div>{missing}</div>\n", encoding="utf-8")
    monkeypatch.setattr(manager, "problems_for", lambda paths, wait=2.5: {paths[0]: {
        "reported": True, "problems": [{"line": 1, "severity": "error", "message": "Cannot find name 'missing'."}]}})
    result = checks.check_syntax(str(path))
    assert result["valid"] is False and "Cannot find name 'missing'" in result["result"]
