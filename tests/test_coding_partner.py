"""Mike as a coding partner: several files at once, room to think, and a
session that doesn't stop for an approval at every edit.

What was missing, measured against what a student asks for -- build this,
debug that, plan our hackathon:
  - reading a task's files, or writing a new project's, took one model call
    per file -- each re-sending the conversation;
  - no room to plan: thinking was off for speed, and nothing replaced it;
  - every edit and every command stopped for an approval card;
  - with no editor connected the coding tools weren't offered at all, even
    when Fast mode's cloud model was answering.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import _isolate  # noqa: F401,E402

from tools.filesystem import edits  # noqa: E402


# ── several files at once ─────────────────────────────────────────────────

def test_read_files_reads_a_tasks_files_in_one_step(tmp_path):
    (tmp_path / "app.py").write_text("from util import add\nprint(add(2, 3))\n", encoding="utf-8")
    (tmp_path / "util.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    out = edits.read_files([str(tmp_path / "app.py"), str(tmp_path / "util.py"),
                            str(tmp_path / "missing.py")])
    assert out["status"] == "success"
    files = out["files"]
    assert "print(add(2, 3))" in files[0]["content"] and "return a - b" in files[1]["content"]
    assert files[1]["content"].startswith("1\t"), "numbered, as read_lines numbers"
    assert "No such file" in files[2]["error"]


def test_read_files_stays_within_its_budget(tmp_path, monkeypatch):
    monkeypatch.setattr(edits, "READ_FILES_BUDGET", 300)
    for name in ("a.txt", "b.txt"):
        (tmp_path / name).write_text("x" * 50 + "\n" * 20, encoding="utf-8")
    big = tmp_path / "big.txt"
    big.write_text("\n".join(f"line {i}" for i in range(200)), encoding="utf-8")
    out = edits.read_files([str(big), str(tmp_path / "a.txt"), str(tmp_path / "b.txt")])
    assert out["files"][0].get("truncated") and "read_lines" in out["note"]
    assert any("skipped" in f for f in out["files"]), "the rest is named, not silently dropped"


def test_write_files_builds_a_project_in_one_step(tmp_path):
    out = edits.write_files([
        {"path": str(tmp_path / "hack" / "app.py"), "content": "print('hi')\n"},
        {"path": str(tmp_path / "hack" / "templates" / "index.html"), "content": "<h1>hi</h1>\n"},
        {"path": str(tmp_path / "hack" / "requirements.txt"), "content": "flask\n"},
    ])
    assert out["status"] == "success" and out["result"] == "Wrote 3 of 3 file(s)."
    assert (tmp_path / "hack" / "templates" / "index.html").read_text(encoding="utf-8") == "<h1>hi</h1>\n"


def test_write_files_replaces_an_open_file_through_the_editor(tmp_path, monkeypatch):
    from ide import manager
    target = tmp_path / "main.py"
    target.write_text("old\n", encoding="utf-8")
    calls = []
    monkeypatch.setattr(manager, "editor_text", lambda p: "old, with unsaved typing\n")
    monkeypatch.setattr(manager, "replace_in_editor",
                        lambda p, s, e, old, new: calls.append((old, new)) or {"ok": True, "problems": []})
    out = edits.write_files([{"path": str(target), "content": "new\n"}])
    assert out["status"] == "success" and out["files"][0]["editor"]
    assert calls and target.read_text(encoding="utf-8") == "old\n", "the editor wrote it, not the disk"


def test_thinking_is_a_step_that_changes_nothing():
    from brain.core_runtime import CoreRuntime
    rt = CoreRuntime()
    out = rt._execute_tool("think", {"thought": "Reproduce first: run app.py, read the traceback."})
    assert out["status"] == "success"


# ── a session that doesn't stop at every edit ────────────────────────────

@pytest.fixture
def project(tmp_path):
    root = tmp_path / "hackathon"
    (root / "src").mkdir(parents=True)
    (root / "package.json").write_text("{}", encoding="utf-8")
    return root


def test_edits_in_one_project_can_be_allowed_for_the_session(project, tmp_path):
    from brain.grants import SessionGrants
    g = SessionGrants()
    edit = {"path": str(project / "src" / "app.js"), "old_text": "a", "new_text": "b"}
    assert g.offer("edit_file", edit) == "Allow edits in hackathon this session"
    assert not g.covers("edit_file", edit)
    g.grant("edit_file", edit)
    assert g.covers("multi_edit", {"path": str(project / "README.md")})
    assert g.covers("write_files", {"files": [{"path": str(project / "src" / "x.js")},
                                              {"path": str(project / "y.css")}]})
    assert not g.covers("edit_file", {"path": str(tmp_path / "elsewhere.py")}), "only that project"
    assert not g.covers("delete_path", {"path": str(project / "src" / "app.js")}), "never deleting"


def test_a_command_can_be_allowed_exactly(project):
    from brain.grants import SessionGrants
    g = SessionGrants()
    assert g.offer("run_command", {"command": "npm   test"}) == "Always allow “npm test” this session"
    g.grant("run_command", {"command": "npm test"})
    assert g.covers("run_command", {"command": "npm test"})
    assert not g.covers("run_command", {"command": "npm test && rm -rf build"})


def test_nothing_as_wide_as_a_home_folder_is_offered():
    from pathlib import Path
    from brain.grants import SessionGrants
    assert SessionGrants().offer("write_file", {"path": str(Path.home() / "notes.txt")}) == ""


def test_the_runtime_asks_once_and_then_the_session_allows_it(project):
    from brain.core_runtime import CoreRuntime
    rt = CoreRuntime()
    asked = []

    def confirm(description):
        asked.append((description, rt.pending_offer))
        return "always"

    edit = {"path": str(project / "src" / "app.js"), "old_text": "a", "new_text": "b"}
    assert rt._approved(confirm, "edit_file", edit)
    assert asked and asked[0][1] == "Allow edits in hackathon this session"
    assert rt._approved(confirm, "write_file", {"path": str(project / "index.html"), "content": ""})
    assert len(asked) == 1, "not asked again inside the project"
    assert rt._approved(lambda d: False, "run_command", {"command": "npm start"}) is False


# ── the cloud model gets the tools; the local one says what it can't do ──

def test_coding_is_on_while_fast_mode_answers(monkeypatch):
    from brain import permissions
    from brain.providers import workers_ai_provider as fast
    monkeypatch.setattr(permissions, "_editor_connected", lambda: False)
    monkeypatch.setattr(fast, "fast_mode_on", lambda: False)
    assert not permissions.is_enabled("coding")
    monkeypatch.setattr(fast, "fast_mode_on", lambda: True)
    monkeypatch.setattr(fast, "_allowance_gone_until", 0.0)
    assert permissions.is_enabled("coding")
    permissions.set_enabled("coding", False)
    try:
        assert not permissions.is_enabled("coding"), "switched off in Settings, it stays off"
    finally:
        permissions.set_enabled("coding", True)
        from config import preferences
        preferences.set_value("abilities_on", "")


def test_switching_to_the_local_model_says_bigger_jobs_are_limited(monkeypatch):
    from brain.providers import workers_ai_provider as fast
    monkeypatch.setattr(fast, "fast_mode_on", lambda: True)
    monkeypatch.setattr(fast, "_allowance_gone_until", 0.0)
    p = fast.WorkersAIProvider(local=type("L", (), {})(), model="m")
    p._answered_by("cloud")
    p._answered_by("local")
    notice = p.take_notice()
    assert "limited" in notice and "coding" in notice


# ── the card ──────────────────────────────────────────────────────────────

def test_the_card_offers_the_session_approval_but_never_for_the_permanent():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)
    from ui.workspace.chat_page import ConfirmCard
    card = ConfirmCard()
    card.ask("Edit app.js", "Allow edits in hackathon this session")
    assert card._always.isVisibleTo(card) and card._always.text() == "Allow edits in hackathon this session"
    card.ask("Delete the folder build. This can't be undone.", "Allow edits in hackathon this session")
    assert not card._always.isVisibleTo(card)
    card.ask("Run npm test")
    assert not card._always.isVisibleTo(card)


def test_vs_codes_own_folder_in_home_does_not_hide_a_project(tmp_path, monkeypatch):
    """VS Code keeps a .vscode folder in the home folder. The search for a
    project's marker reached it, the home folder was (rightly) refused -- and
    the offer to allow edits was dropped for every project without a marker."""
    from pathlib import Path
    from brain.grants import SessionGrants
    home = tmp_path / "home"
    (home / ".vscode").mkdir(parents=True)
    proj = home / "source" / "calc"
    (proj / "calc").mkdir(parents=True)
    (proj / "tests").mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    edit = {"path": str(proj / "calc" / "stats.py"), "old_text": "a", "new_text": "b"}
    assert SessionGrants().offer("edit_file", edit) == "Allow edits in calc this session"


def test_the_folder_the_tests_ran_in_is_the_project(tmp_path, monkeypatch):
    """No marker file: the folder commands ran in, with the student's OK, is
    the project as they work it -- the tests next to the code included."""
    from pathlib import Path
    from brain.grants import SessionGrants
    home = tmp_path / "home"
    proj = home / "source" / "calc"
    (proj / "calc").mkdir(parents=True)
    (proj / "tests").mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    g = SessionGrants()
    g.note_approved("run_command", {"command": "python -m unittest", "cwd": str(proj)})
    g.grant("edit_file", {"path": str(proj / "calc" / "stats.py")})
    assert g.covers("edit_file", {"path": str(proj / "tests" / "test_stats.py")})
    assert not g.covers("edit_file", {"path": str(home / "source" / "other.py")})


def test_the_local_model_keeps_the_coding_tools_when_the_allowance_runs_out(monkeypatch):
    """The same tools either side of the switch: a coding task carries on
    (slower), and the local model's saved reading of the prompt still fits --
    taking the tools away changed the prompt, and it was read again (171s)."""
    import time
    from brain import permissions
    from brain.providers import workers_ai_provider as fast
    monkeypatch.setattr(permissions, "_editor_connected", lambda: False)
    monkeypatch.setattr(fast, "fast_mode_on", lambda: True)
    monkeypatch.setattr(fast, "_allowance_gone_until", time.time() + 3600)
    assert not fast.allowance_left()
    assert permissions.is_enabled("coding")
