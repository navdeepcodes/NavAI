"""Launch readiness: the things a shipped desktop app must get right.

One Mike at a time; crashes recorded; logs that don't grow forever; the
permissions you set actually enforced; your data exportable and erasable;
the legal documents present, bundled and truthful about the network.
"""
from __future__ import annotations

import os
import sys
import time
import uuid

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


# ── one Mike at a time ────────────────────────────────────────

def test_a_second_launch_hands_over_to_the_running_mike():
    app = _app()
    from ui.system.lifecycle import SingleInstance

    name = f"MikeTest-{uuid.uuid4().hex[:8]}"
    first = SingleInstance(name)
    assert first.claim(), "the first launch is Mike"
    shown = []
    first.activated.connect(lambda: shown.append(1))

    second = SingleInstance(name)
    assert not second.claim(), "a second launch must not start another Mike"
    _pump(app, 0.4)
    assert shown, "the running Mike is asked to come forward"
    first.release()

    third = SingleInstance(name)
    assert third.claim(), "once Mike has quit, the next launch is Mike again"
    third.release()


# ── crashes and logs ──────────────────────────────────────────

def test_uncaught_exceptions_are_logged_not_lost():
    import logging
    from ui.system import lifecycle

    lifecycle.install_crash_handlers()
    records = []

    class Grab(logging.Handler):
        def emit(self, record):
            records.append(record)

    h = Grab()
    logging.getLogger("Mike").addHandler(h)
    try:
        try:
            raise ValueError("boom")
        except ValueError:
            sys.excepthook(*sys.exc_info())
    finally:
        logging.getLogger("Mike").removeHandler(h)
    assert any(r.exc_info and r.exc_info[0] is ValueError for r in records)
    assert os.path.exists(lifecycle.crash_log_path())


def test_the_log_rotates_instead_of_growing_forever():
    from logging.handlers import RotatingFileHandler
    import logging

    handlers = logging.getLogger().handlers
    rot = [h for h in handlers if isinstance(h, RotatingFileHandler)]
    assert rot and rot[0].maxBytes > 0 and rot[0].backupCount >= 1


# ── permissions are enforced, not just hidden ─────────────────

def test_every_tool_belongs_to_a_permission():
    from brain.core_tools import OLLAMA_TOOLS
    from brain import permissions

    always = {"calculate"}          # pure arithmetic, touches nothing
    for tool in OLLAMA_TOOLS:
        name = tool["function"]["name"]
        assert name in always or permissions.ability_of(name), (
            f"{name} isn't governed by any permission")


def test_a_turned_off_ability_is_hidden_and_refused():
    from brain import permissions
    from brain.core_runtime import CoreRuntime
    from brain.core_tools import OLLAMA_TOOLS

    permissions.set_enabled("commands", False)
    try:
        names = {t["function"]["name"] for t in permissions.allowed_tools(OLLAMA_TOOLS)}
        assert "run_command" not in names, "the model is never offered it"
        assert "read_file" in names, "other abilities are untouched"

        rt = CoreRuntime.__new__(CoreRuntime)
        result = rt._execute_tool("run_command", {"command": "echo hi"})
        assert result["status"] == "error" and "Permissions" in result["error"], (
            "and a call anyway is refused before anything runs")
    finally:
        permissions.set_enabled("commands", True)
    assert "run_command" in {t["function"]["name"]
                             for t in permissions.allowed_tools(OLLAMA_TOOLS)}


# ── your data: exportable, erasable ───────────────────────────

def test_export_contains_your_chats_and_reset_erases_everything(tmp_path):
    import json
    import zipfile
    from brain import conversation_store as cs, data_export
    from config import preferences

    cid = cs.create()
    cs.add_message(cid, "user", "notes on bernoulli")
    preferences.set_value("profile_name", "Sam")
    path = data_export.export_zip(tmp_path / "export.zip")
    with zipfile.ZipFile(path) as zf:
        chats = json.loads(zf.read("chats.json"))
        assert any(m["content"] == "notes on bernoulli" for c in chats for m in c["messages"])
        assert {"memory.json", "activity.json", "preferences.json", "README.txt"} <= set(zf.namelist())

    data_export.reset_everything()
    assert cs.recent() == [], "reset erases every chat"
    assert preferences.get("profile_name") == "", "and settings return to defaults"


def test_a_problem_report_leaves_out_who_you_are(tmp_path):
    import json
    import zipfile
    from brain import support_bundle
    from config import preferences

    preferences.set_value("profile_name", "Sam Student")
    path = support_bundle.create(tmp_path / "report.zip")
    with zipfile.ZipFile(path) as zf:
        settings = json.loads(zf.read("settings.json"))
        assert "profile_name" not in settings and "profile_about" not in settings
        assert "system.json" in zf.namelist()
    preferences.set_value("profile_name", "")


# ── legal: present, bundled, truthful ─────────────────────────

def test_legal_documents_ship_filled_in_and_bundled():
    from brain import legal

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = open(os.path.join(here, "packaging", "mike.spec"), encoding="utf-8").read()
    assert '"docs", "legal"' in spec, "the documents must ship inside the app"
    for key in legal.DOCS:
        text = legal.load(key)
        assert len(text) > 500 and "couldn't be found" not in text
        for token in ("{publisher}", "{version}", "{updated}", "{contact}", "{data_dir}"):
            assert token not in text


def test_the_privacy_policy_names_every_place_mike_connects_to():
    """If Mike gains a new internet destination, this policy must say so."""
    from brain import legal

    policy = " ".join(legal.load("privacy").split())      # ignore line wrapping
    for destination in ("Ollama", "Hugging Face", "Bing", "Google News", "Gmail"):
        assert destination in policy, f"the policy never mentions {destination}"
    assert "telemetry" in policy.lower()


def test_consent_is_asked_and_remembered():
    _app()
    from brain import legal
    from config import preferences
    from ui.welcome import CONSENT, WelcomeWindow

    preferences.set_value("terms_accepted_version", "")
    w = WelcomeWindow(consent_only=True)
    assert w._cards == [CONSENT]
    declined = []
    w.declined.connect(lambda: declined.append(1))
    w._skip_pressed()                      # "Quit" on the consent card
    assert declined and not legal.accepted()

    w2 = WelcomeWindow(consent_only=True)
    w2._advance()                          # "Agree and start"
    assert legal.accepted()

    tour = WelcomeWindow()
    assert CONSENT not in tour._cards, "once agreed, the tour doesn't ask again"


# ── startup and health ────────────────────────────────────────

def test_launch_at_sign_in_is_only_offered_where_it_works():
    import platform
    from hostplatform import autostart

    if platform.system() != "Windows" or not getattr(sys, "frozen", False):
        assert not autostart.supported()
        assert autostart.set_enabled(True) is False
        assert autostart.is_enabled() is False


def test_brain_health_explains_each_situation(monkeypatch):
    from brain import diagnostics, ollama_launcher
    from ui.workspace.health import BrainHealth

    def probe(reachable, pulled, installed):
        monkeypatch.setattr(diagnostics, "check_brain", lambda: {
            "reachable": reachable, "model_pulled": pulled, "model": "qwen", "detail": ""})
        monkeypatch.setattr(ollama_launcher, "installed", lambda: installed)
        return BrainHealth._probe()

    assert probe(True, True, True)["state"] == "ready"
    assert probe(True, False, True)["state"] == "no_model"
    nr = probe(False, False, True)
    assert nr["state"] == "not_running" and nr["can_start"]
    assert probe(False, False, False)["state"] == "not_installed"
