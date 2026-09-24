"""Conversations survive a restart, a new chat is really new, and an old
chat's summary can never leak into a different one.

Found in the production-readiness pass, using the real app like a student:

* Everything Mike knew about a conversation lived only in RAM, so "close Mike,
  reopen, carry on" was impossible, and Ctrl+L cleared the screen while Mike
  silently kept the whole conversation in context.
* The running situation summary was one global row loaded at startup, so the
  summary of a days-old test chat ("the user says nothing is going right…")
  was injected into every turn of every later session. A student's first
  "hey mike" was answered "rough day?", and algebra answers ended "want a
  distraction?".

Driven through the real UIController and the real workspace; only the model
call is replaced, so a turn can complete offline.
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401


def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


def _pump(app, seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


# ── the store ─────────────────────────────────────────────────

def test_store_roundtrip_titles_and_order():
    from brain import conversation_store as cs

    a = cs.create()
    cs.add_message(a, "user", "explain mitosis vs meiosis simply", ["notes.pdf"])
    cs.add_message(a, "assistant", "Mitosis copies; meiosis halves.")
    b = cs.create()
    cs.add_message(b, "user", "solve 2x^2 - 8 = 0")

    got = cs.get(a)
    assert got["title"] == "explain mitosis vs meiosis simply"
    msgs = cs.messages(a)
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[0]["attachments"] == ["notes.pdf"]
    ids = [c["id"] for c in cs.recent()]
    assert ids.index(b) < ids.index(a), "most recently used chat comes first"
    assert cs.latest()["id"] == b


def test_empty_conversation_is_never_listed():
    from brain import conversation_store as cs

    empty = cs.create()
    assert empty not in [c["id"] for c in cs.recent()]


def test_delete_removes_chat_and_its_messages():
    from brain import conversation_store as cs

    c = cs.create()
    cs.add_message(c, "user", "delete me")
    cs.delete(c)
    assert cs.get(c) is None
    assert cs.messages(c) == []


# ── the stale-summary leak ─────────────────────────────────────

def test_old_global_summary_is_not_loaded_into_a_new_session():
    from brain import situation_store
    from brain.mike_core import MikeCore

    situation_store.save(
        "The user confirms today has been rough because nothing is going right.",
        project_id=None,
    )
    core = MikeCore(host="http://127.0.0.1:11434", summary_model="x")
    assert core.situation_summary == "", (
        "a new session must not inherit another conversation's summary")


def test_reset_and_restore_conversation():
    from brain.mike_core import MikeCore

    core = MikeCore(host="http://127.0.0.1:11434", summary_model="x")
    core.history = [{"role": "user", "content": "old"}]
    core.situation_summary = "old summary"
    core.tool_log = ["Opened notepad"]
    epoch = core._epoch

    core.reset_conversation()
    assert core.history == [] and core.situation_summary == "" and core.tool_log == []
    assert core._epoch == epoch + 1

    core.restore_conversation(
        [{"role": "user", "content": "hi"},
         {"role": "system", "content": "volatile snapshot — not restored"},
         {"role": "assistant", "content": "hey"}],
        summary="talked about cells",
    )
    assert [m["role"] for m in core.history] == ["user", "assistant"]
    assert core.situation_summary == "talked about cells"


def test_summary_refresh_from_an_old_chat_is_discarded(monkeypatch):
    """A background summary that finishes after the user started a new chat
    must not land on the new chat."""
    from brain.mike_core import MikeCore
    import brain.providers as providers

    class _Result:
        error = None
        text = "Summary of the OLD chat."

    class _Provider:
        def complete(self, _messages):
            return _Result()

    monkeypatch.setattr(providers, "get_provider", lambda **_k: _Provider())
    core = MikeCore(host="http://127.0.0.1:11434", summary_model="x")
    started_in = core._epoch
    core.reset_conversation()          # user hit New chat mid-refresh
    core._refresh_summary("", [{"role": "user", "content": "x"}], None, started_in)
    assert core.situation_summary == ""


# ── through the real controller ────────────────────────────────

def _controller(monkeypatch):
    app = _app()
    from config import preferences
    preferences.set_value("voice_enabled", False)      # tests must not talk

    from brain.core_runtime import CoreRuntime
    from ui.controller.ui_controller import UIController
    from ui.workspace.workspace import MikeWorkspace

    runtime = CoreRuntime()

    def fake_stream(message, confirm_callback=None, cancel_event=None):
        # Mimic the runtime's own bookkeeping, then stream a reply.
        runtime._core.history.append({"role": "user", "content": message})
        reply = f"You said: {message}"
        runtime._core.history.append({"role": "assistant", "content": reply})
        for word in reply.split(" "):
            yield ("token", word + " ")

    monkeypatch.setattr(runtime, "process_streaming", fake_stream)
    page = MikeWorkspace({})
    return app, UIController(runtime, page), runtime, page


def _run_turn(app, controller, text):
    controller.process_message(text)
    t0 = time.time()
    while controller._worker is not None and time.time() - t0 < 10:
        _pump(app, 0.05)
    _pump(app, 0.1)


def test_a_turn_is_saved_and_a_new_chat_really_forgets(monkeypatch):
    from brain import conversation_store as cs

    app, controller, runtime, _page = _controller(monkeypatch)
    _run_turn(app, controller, "remember the word banana")
    cid = controller.conversation_id
    assert cid is not None
    msgs = cs.messages(cid)
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["content"].startswith("You said: remember the word banana")

    controller.new_conversation()
    assert controller.conversation_id is None
    assert runtime._core.history == [], "a new chat must not carry the old one"


def test_reopening_restores_screen_and_context(monkeypatch):
    from brain import conversation_store as cs
    from ui.workspace.chat_page import _UserBubble
    from ui.panel.mike_panel import _RichTurn

    app, controller, runtime, page = _controller(monkeypatch)
    _run_turn(app, controller, "my exam is on friday")
    cid = controller.conversation_id
    cs.set_summary(cid, "Student has an exam on Friday.")

    controller.new_conversation()
    controller.open_conversation(cid)

    assert controller.conversation_id == cid
    contents = [m["content"] for m in runtime._core.history]
    assert "my exam is on friday" in contents
    assert runtime.situation_summary == "Student has an exam on Friday."

    lay = page.chat._stage
    kinds = [type(lay.itemAt(i).widget()) for i in range(lay.count())
             if lay.itemAt(i).widget() is not None]
    assert _UserBubble in kinds and _RichTurn in kinds

    # Continuing appends to the same chat rather than starting a new one.
    _run_turn(app, controller, "what day is my exam?")
    assert controller.conversation_id == cid
    assert len(cs.messages(cid)) == 4


def test_launch_resumes_only_a_recent_chat(monkeypatch):
    from brain import conversation_store as cs

    app, controller, runtime, _page = _controller(monkeypatch)
    recent = cs.create()
    cs.add_message(recent, "user", "recent chat")
    controller.resume_recent_conversation()
    assert controller.conversation_id == recent

    # A chat last touched two days ago is left in History, not reopened.
    app, controller2, _rt, _p = _controller(monkeypatch)
    cs._db().execute("UPDATE conversations SET updated_at = ?",
                     (time.time() - 48 * 3600,))
    cs._db().commit()
    controller2.resume_recent_conversation()
    assert controller2.conversation_id is None


def test_deleting_a_chat_takes_two_clicks():
    """One stray click must never permanently erase a chat."""
    _app()
    from brain import conversation_store as cs
    from ui.workspace.pages import HistoryPage, _ConvoRow

    cid = cs.create()
    cs.add_message(cid, "user", "important revision notes")
    page = HistoryPage({})
    rows = [r for r in page.findChildren(_ConvoRow) if r._id == cid]
    assert rows, "the chat is listed"
    from PySide6.QtWidgets import QPushButton
    x = [b for b in rows[0].findChildren(QPushButton) if b.text() == "✕"][0]

    x.click()
    assert cs.get(cid) is not None, "first click only asks"
    assert x.text() == "Delete?"
    x.click()
    assert cs.get(cid) is None, "second click deletes"
