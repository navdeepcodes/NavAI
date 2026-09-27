"""Coding in the student's editor: the editor's text is the truth.

A file open in VS Code may hold changes not saved yet. Read from disk and
written back, Mike's edit was made to the older text and the editor then held
two versions -- the student's unsaved work, or Mike's change, was lost. Open
files are now read from the editor and edited through it; the edit is saved,
undoable there, and comes back with what VS Code's checker says about it.
"""
from __future__ import annotations

import os
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import _isolate  # noqa: F401,E402

from ide import manager  # noqa: E402
from tools.filesystem import edits  # noqa: E402

ON_DISK = "a = 1\nb = 2\n"
IN_EDITOR = "a = 1\nb = 2\nc = 3  # typed, not saved\n"


@pytest.fixture
def editor(tmp_path, monkeypatch):
    path = tmp_path / "calc.py"
    path.write_text(ON_DISK, encoding="utf-8")
    state = {"text": IN_EDITOR, "calls": [], "answer": {"ok": True, "problems": []}}

    def editor_text(p):
        return state["text"] if manager._same_file(p, str(path)) and state["text"] is not None else None

    def replace_in_editor(p, start, end, old, new):
        state["calls"].append((start, end, old, new))
        return state["answer"]

    monkeypatch.setattr(manager, "editor_text", editor_text)
    monkeypatch.setattr(manager, "replace_in_editor", replace_in_editor)
    state["path"] = path
    return state


def test_an_edit_is_made_to_what_the_student_sees_not_the_older_file(editor):
    result = edits.edit_file(str(editor["path"]), "b = 2", "b = 20")
    assert result["status"] == "success"
    # the smallest change, at the editor's position: line 1, after "b = 2"
    assert editor["calls"] == [((1, 5), (1, 5), "", "0")]
    assert "typed, not saved" in result["diff"], "the unsaved line was part of the text edited"
    assert editor["path"].read_text(encoding="utf-8") == ON_DISK, "the disk was not written behind the editor"
    assert "Ctrl+Z" in result["editor"]


def test_the_edit_comes_back_with_what_vs_code_reports(editor):
    editor["answer"] = {"ok": True, "problems": [
        {"line": 2, "severity": "error", "message": "\"bb\" is not defined", "source": "Pylance"}]}
    result = edits.edit_file(str(editor["path"]), "b = 2", "b = bb")
    assert "line 2: error" in result["problems"] and "Pylance" in result["problems"]
    editor["answer"] = {"ok": True, "problems": []}
    assert "no errors" in edits.edit_file(str(editor["path"]), "a = 1", "a = 2")["problems"]


def test_text_that_changed_meanwhile_is_not_overwritten(editor):
    editor["answer"] = {"ok": False, "changed": True}
    result = edits.edit_file(str(editor["path"]), "b = 2", "b = 20")
    assert result["status"] == "error" and "changed in the editor" in result["error"]
    assert editor["path"].read_text(encoding="utf-8") == ON_DISK


def test_a_file_not_open_in_the_editor_is_edited_on_disk(editor):
    editor["text"] = None
    result = edits.edit_file(str(editor["path"]), "b = 2", "b = 20")
    assert result["status"] == "success" and editor["calls"] == []
    assert editor["path"].read_text(encoding="utf-8") == "a = 1\nb = 20\n"


def test_several_edits_arrive_as_one_change(editor):
    result = edits.multi_edit(str(editor["path"]), [
        {"old_text": "a = 1", "new_text": "a = 10"}, {"old_text": "c = 3", "new_text": "c = 30"}])
    assert result["status"] == "success" and len(editor["calls"]) == 1
    (start, end, old, new) = editor["calls"][0]
    assert start == (0, 5) and old == "\nb = 2\nc = 3" and new == "0\nb = 2\nc = 30"


def test_reading_shows_the_unsaved_lines(editor):
    shown = edits.read_lines(str(editor["path"]))
    assert "typed, not saved" in shown["content"] and shown["total_lines"] == 3


def test_editor_columns_count_like_the_editor():
    # VS Code counts UTF-16 units: an emoji is two.
    assert edits._position("x = '😀'; y = 1", len("x = '😀'; y")) == (0, 11)


# ── asking from the editor ───────────────────────────────────────────────

def _free_port() -> int:
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_a_question_asked_in_the_editor_reaches_mike():
    import requests
    from ide.bridge import IDEBridge
    bridge = IDEBridge(port=_free_port())
    assert bridge.start()
    try:
        url = f"http://127.0.0.1:{bridge._port}/ask"
        assert requests.post(url, json={"question": "why does this crash?"}, timeout=5).status_code == 503
        asked = []
        bridge.on_ask = asked.append
        r = requests.post(url, json={"question": "why does this crash?"}, timeout=5)
        assert r.status_code == 200 and asked == ["why does this crash?"]
    finally:
        bridge.stop()


def test_the_question_is_answered_on_the_ui_thread(monkeypatch):
    from PySide6.QtWidgets import QApplication

    from brain.core_runtime import CoreRuntime
    from ui.controller.ui_controller import UIController
    from ui.panel.mike_panel import MikePanel

    app = QApplication.instance() or QApplication(sys.argv)
    ctrl = UIController(CoreRuntime(), MikePanel({}))
    got = []
    # Plain Python for "which thread": a Qt call here can surface errors from
    # earlier tests' deleted windows, still firing their timers.
    monkeypatch.setattr(ctrl, "process_message", lambda text, by_voice=False: got.append(
        (text, threading.current_thread() is threading.main_thread())))
    asker = threading.Thread(target=manager._bridge.on_ask, args=("explain line 12",))
    asker.start()
    asker.join()
    deadline = time.monotonic() + 2
    while not got and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert got == [("explain line 12", True)]


# ── keeping the extension current ────────────────────────────────────────

def test_an_older_extension_is_updated_and_a_removed_one_left_alone(monkeypatch):
    from config import preferences
    from ide import install
    runs = []
    monkeypatch.setattr(install, "find_vscode_cli", lambda: "code")
    monkeypatch.setattr(install, "bundled_vsix", lambda: "mike-bridge.vsix")

    class _Done:
        returncode, stdout, stderr = 0, "", ""
    monkeypatch.setattr(install.subprocess, "run", lambda *a, **k: runs.append(a[0]) or _Done())

    monkeypatch.setattr(install, "installed_version", lambda cli: "0.1.0")
    changed, why = install.ensure_installed()
    assert changed and "updated" in why and any("--install-extension" in r for r in runs)

    runs.clear()
    monkeypatch.setattr(install, "installed_version", lambda cli: install.EXTENSION_VERSION)
    assert install.ensure_installed() == (False, "the extension is already installed and up to date")

    preferences.set_value("vscode_extension_offered", True)
    monkeypatch.setattr(install, "installed_version", lambda cli: None)
    assert install.ensure_installed()[0] is False and runs == [], "removed on purpose: not put back"
