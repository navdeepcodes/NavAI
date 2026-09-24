"""The workspace behaves like a finished product, not just renders like one.

Pinned from the production polish pass, each against the real widgets:

* Typography: a font rule on the universal QWidget selector silently
  overrode every setFont() in the app, so every title and label rendered at
  one size. Guarded so it can't come back.
* The rail lists conversations only, reopens them, folds away (and stays
  folded across launches), and everything else lives in Settings.
* Changing the theme inside Settings keeps you in Settings, on the same tab.
* Stop is always on screen while Mike works or speaks, and Stop / Esc
  silences a voice still reading a finished answer.
* The steps card never leaves a step "running" after the turn ends, folds a
  successful run away, and keeps a failure open.
* Every tool Mike can call is labelled in plain words — no function names, no
  element ids — with paths shortened to a file and its folder.
* The Reduce motion switch is read by the thing it claims to control.
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


def _pump(app, seconds=0.05):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


# ── typography ────────────────────────────────────────────────

def test_the_global_stylesheet_never_pins_fonts_on_every_widget():
    import re
    from ui.theme.stylesheet import GLOBAL_STYLESHEET

    block = re.search(r"(?m)^QWidget \{\{?(.*?)\}", GLOBAL_STYLESHEET, re.S)
    assert block is not None
    body = block.group(1)
    assert "font-size" not in body and "font-family" not in body, (
        "a font on the universal QWidget rule overrides every widget's setFont()")


def test_workspace_titles_actually_get_their_size():
    _app()
    from ui.panel import style
    from ui.workspace.pages import SettingsPage
    from PySide6.QtWidgets import QLabel

    page = SettingsPage({})
    titles = [lbl for lbl in page.findChildren(QLabel) if lbl.text() == "Settings"]
    assert titles and titles[0].font().pixelSize() == style.DISPLAY


# ── the rail ──────────────────────────────────────────────────

def test_the_rail_lists_conversations_and_reopens_them():
    _app()
    from brain import conversation_store as cs
    from ui.workspace.workspace import MikeWorkspace

    cid = cs.create()
    cs.add_message(cid, "user", "integrate x squared")
    opened = []
    page = MikeWorkspace({"open_conversation": opened.append})
    rows = {r.conversation_id: r for r in page.sidebar.rows()}
    assert cid in rows
    rows[cid].opened.emit(cid)
    assert opened == [cid]

    page.conversation_changed(cid)
    assert page._title.text() == "integrate x squared"


def test_the_rail_folds_and_remembers_it():
    _app()
    from config import preferences
    from ui.workspace.workspace import MikeWorkspace

    preferences.set_value("sidebar_collapsed", False)
    page = MikeWorkspace({})
    assert page.sidebar_open()
    assert page._unfold.isHidden(), "no second toggle while the rail is open"

    page.toggle_sidebar()
    assert not page.sidebar_open()
    assert preferences.get("sidebar_collapsed") is True
    assert not page._unfold.isHidden(), "the way back appears in the titlebar"

    again = MikeWorkspace({})
    assert not again.sidebar_open(), "a folded rail stays folded on relaunch"
    preferences.set_value("sidebar_collapsed", False)


def test_settings_holds_everything_that_is_not_a_conversation():
    _app()
    from ui.workspace.pages import SettingsPage

    keys = [k for k, _ in SettingsPage.TABS]
    assert keys == ["general", "voice", "memory", "activity", "privacy", "about"]
    page = SettingsPage({})
    for key in keys:
        page.open_tab(key)
        assert page.current_tab() == key


def test_changing_the_theme_keeps_you_in_settings_on_the_same_tab():
    _app()
    from config import preferences
    from ui.workspace.workspace import MikeWorkspace

    page = MikeWorkspace({})
    page.open_settings("general")
    page._settings._tabs["general"]._set_theme("dark")
    assert page.showing_overlay(), "the theme change must not drop you into the chat"
    assert page._settings.current_tab() == "general"
    page._settings._tabs["general"]._set_theme("light")
    preferences.set_value("theme", "system")


# ── the composer ──────────────────────────────────────────────

def test_enter_sends_and_shift_enter_starts_a_new_line():
    app = _app()
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent
    from ui.workspace.composer import Composer

    c = Composer()
    sent = []
    c.submitted.connect(sent.append)
    c.set_text("line one")
    c._field.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.ShiftModifier))
    c._field.insertPlainText("line two")
    assert sent == []
    c._field.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier))
    assert sent == ["line one\nline two"]
    assert c.text() == ""
    _pump(app)


def test_the_send_button_becomes_stop_while_mike_works():
    _app()
    from ui.workspace.composer import Composer

    c = Composer()
    stops, sent = [], []
    c.stop_requested.connect(lambda: stops.append(1))
    c.submitted.connect(sent.append)
    assert not c._send.isEnabled(), "nothing to send yet"
    c.set_responding(True)
    assert c._send.isEnabled() and c._send._icon == "stop"
    c._send.click()
    assert stops == [1] and sent == []
    c.set_responding(False)
    assert c._send._icon == "send"


def test_the_mic_only_claims_speaking_when_voice_is_on():
    _app()
    from config import preferences
    from ui.workspace.composer import MicButton

    mic = MicButton()
    preferences.set_value("voice_enabled", False)
    mic.set_state("speaking")
    assert mic.voice_state() == "idle"
    preferences.set_value("voice_enabled", True)
    mic.set_state("speaking")
    assert mic.voice_state() == "speaking"
    mic.set_state("recording")
    assert mic.voice_state() == "recording"
    preferences.set_value("voice_enabled", False)


# ── Stop really stops ─────────────────────────────────────────

class _Talking:
    def __init__(self) -> None:
        self.stopped = False

    def is_speaking(self):
        return not self.stopped

    def stop(self):
        self.stopped = True

    def speak_sentence(self, _t):
        pass

    def finish_streaming(self):
        pass

    def pump(self):
        pass

    def reset_health(self):
        pass

    def shutdown(self):
        pass

    @property
    def streaming_done(self):
        return True


def test_stop_silences_a_voice_reading_a_finished_answer():
    _app()
    from brain.core_runtime import CoreRuntime
    from ui.controller.ui_controller import UIController
    from ui.workspace.workspace import MikeWorkspace

    page = MikeWorkspace({})
    controller = UIController(CoreRuntime(), page)
    speaker = _Talking()
    controller._speaker = speaker
    controller._speech_pump_timer.start()
    page.set_state("speaking")
    assert controller._worker is None

    page.input.stop_requested.emit()          # the Stop button
    assert speaker.stopped, "Stop must silence Mike even with no turn running"
    assert page.state() == "idle"
    controller.shutdown()


def test_stopping_a_turn_marks_its_running_step_stopped():
    _app()
    from ui.workspace.chat_page import ChatPage

    page = ChatPage()
    page.add_user_message("open blender")
    handle = page.add_action_card("Opening Blender")
    assert page._ledger.is_running()
    page.mark_stopped()
    page.set_state("idle")
    assert not page._ledger.is_running(), "no step may be left turning after Stop"
    assert page._ledger.outcome() == "stopped"
    assert handle is not None


# ── the steps card ────────────────────────────────────────────

def test_a_successful_run_folds_away_and_a_failure_stays_open():
    _app()
    from ui.workspace.steps import StepsCard

    ok = StepsCard()
    for t in ("Reading notes.pdf", "Writing cards.md in Desktop"):
        i = ok.add_row(t)
        ok.set_status(i, "done")
    ok.settle("done")
    assert ok.outcome() == "done" and ok._collapsed
    assert all(r.isHidden() for r in ok._rows)
    ok._toggle()
    assert not ok._collapsed, "a folded run opens again on click"

    bad = StepsCard()
    a = bad.add_row("Opening File Explorer")
    bad.set_status(a, "done")
    b = bad.add_row("Writing notes.md in Physics")
    bad.set_status(b, "failed")
    bad.settle("done")
    assert bad.outcome() == "failed" and not bad._collapsed


def test_a_turn_ending_settles_the_card_even_without_a_final_status():
    _app()
    from ui.workspace.chat_page import ChatPage

    page = ChatPage()
    page.add_user_message("do it")
    page.add_action_card("Looking at the window")
    page.set_state("idle")                    # the turn ended
    assert not page._ledger.is_running()


# ── plain-language tool labels ────────────────────────────────

def test_every_tool_is_named_in_plain_words():
    from brain.core_tools import OLLAMA_TOOLS, friendly_tool_name

    for tool in OLLAMA_TOOLS:
        name = tool["function"]["name"]
        label = friendly_tool_name(name, {})
        assert "Executing" not in label, f"{name} is shown as {label!r}"
        assert name not in label, f"{name} leaks its function name: {label!r}"
        assert label and label[0].isupper()


def test_paths_are_shown_as_a_file_and_its_folder():
    from brain.core_tools import friendly_tool_name

    label = friendly_tool_name(
        "write_file", {"path": r"C:\Users\sam\Documents\Physics\notes.md"})
    assert label == "Writing notes.md in Physics"
    assert friendly_tool_name("open_url", {"url": "https://www.youtube.com/"}) == "Opening youtube.com"
    assert friendly_tool_name("press_keys", {"key": "s", "modifiers": ["ctrl"]}) == "Pressing Ctrl+S"


def test_a_click_names_the_element_not_its_reference(monkeypatch):
    from brain.core_tools import friendly_tool_name
    from computer import session

    monkeypatch.setattr(session.SESSION, "element_label",
                        lambda ref: "Save" if ref == "el7" else "")
    assert friendly_tool_name("click_element", {"ref": "el7"}) == "Clicking “Save”"
    assert "el9" not in friendly_tool_name("click_element", {"ref": "el9"})


# ── calm mode ─────────────────────────────────────────────────

def test_the_reduce_motion_switch_is_actually_read():
    from config import preferences
    from ui.panel import style

    preferences.set_value("reduced_motion", True)
    assert style.reduced_motion()
    preferences.set_value("reduced_motion", False)


# ── a sentence before a tool is not repeated in the answer ────

def test_the_answer_bubble_holds_only_its_own_words(monkeypatch):
    """Mike often says a sentence, uses a tool, then answers. The final bubble
    was given the whole turn's text, so the first sentence appeared twice."""
    app = _app()
    from config import preferences
    preferences.set_value("voice_enabled", False)
    from brain.core_runtime import CoreRuntime
    from ui.controller.ui_controller import UIController
    from ui.panel.mike_panel import _RichTurn
    from ui.workspace.workspace import MikeWorkspace

    runtime = CoreRuntime()

    def scripted(message, confirm_callback=None, cancel_event=None):
        runtime._core.history.append({"role": "user", "content": message})
        yield ("token", "I'll set that up. ")
        yield ("tool_start", "Opening File Explorer")
        yield ("tool_end", "done")
        yield ("token", "Done — it's open.")

    monkeypatch.setattr(runtime, "process_streaming", scripted)
    page = MikeWorkspace({})
    controller = UIController(runtime, page)
    controller.process_message("open explorer")
    t0 = time.time()
    while controller._worker is not None and time.time() - t0 < 10:
        _pump(app, 0.05)
    _pump(app, 0.1)

    lay = page.chat._stage
    texts = [lay.itemAt(i).widget().text() for i in range(lay.count())
             if isinstance(lay.itemAt(i).widget(), _RichTurn)]
    assert texts == ["I'll set that up. ", "Done — it's open."], texts
    controller.shutdown()


# ── Mike's typeface ───────────────────────────────────────────

def test_the_bundled_serif_loads_and_becomes_mikes_face():
    """Source Serif 4 ships in ui/fonts (OFL) and is registered at startup, so
    Mike looks the same on every machine instead of on whatever is installed."""
    _app()
    from ui.panel import style

    assert style.load_fonts(), "the bundled Source Serif 4 files must load"
    assert style.ui_face() == style.BRAND_FAMILY == "Source Serif 4"
    assert style.font(style.BODY).family() == "Source Serif 4"
    assert "Source Serif 4" in style.ui_family(), "rich-text replies use it too"
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert os.path.isfile(os.path.join(here, "ui", "fonts", "OFL.txt")), (
        "the font's licence ships with it")
    spec = open(os.path.join(here, "packaging", "mike.spec")).read()
    assert '"ui", "fonts"' in spec, "the Windows package must bundle the fonts"
