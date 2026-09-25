"""Mike accounts, without a server: switched off until configured, the saved
sign-in handled safely, errors explained, Google's loopback and PKCE correct,
the sign-in card's own checks, the startup gate, and the legal and data
controls that mention accounts.

The flows against a real Supabase are in tests/test_account_e2e.py.
"""
from __future__ import annotations

import base64
import hashlib
import os
import stat
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import _isolate  # noqa: F401,E402


@pytest.fixture()
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture()
def fresh(monkeypatch):
    """A clean account state; accounts off unless a test turns them on."""
    from account import manager as m
    from account import session_store
    from config import settings
    monkeypatch.setattr(settings, "SUPABASE_URL", "")
    monkeypatch.setattr(settings, "SUPABASE_ANON_KEY", "")
    monkeypatch.setattr(settings, "SUPABASE_OAUTH_PROVIDERS", [])
    monkeypatch.setattr(settings, "ACCOUNT_REQUIRED", False)
    session_store.clear()
    m.reset_for_tests()
    yield
    m.reset_for_tests()


def _configure(monkeypatch, required=False, providers=()):
    from config import settings
    monkeypatch.setattr(settings, "SUPABASE_URL", "http://127.0.0.1:9")  # nothing listens
    monkeypatch.setattr(settings, "SUPABASE_ANON_KEY", "anon-key")
    monkeypatch.setattr(settings, "SUPABASE_OAUTH_PROVIDERS", list(providers))
    monkeypatch.setattr(settings, "ACCOUNT_REQUIRED", required)


# ── switched off until configured ───────────────────────────────────────

def test_accounts_are_hidden_until_a_project_is_configured(app, fresh, monkeypatch):
    from account import config
    from account.manager import manager
    from ui.workspace.pages import SettingsPage

    assert not config.configured() and not config.required()
    assert "account" not in dict(SettingsPage.tabs())
    m = manager()
    m.restore()
    assert m.status == "unavailable" and not m.signed_in()

    _configure(monkeypatch)
    assert SettingsPage.tabs()[0] == ("account", "Account")
    assert not config.required(), "optional unless the build says otherwise"


def test_required_needs_a_project_too(fresh, monkeypatch):
    from account import config
    from config import settings
    monkeypatch.setattr(settings, "ACCOUNT_REQUIRED", True)
    assert not config.required(), "a build can't require an account it can't offer"


# ── the saved sign-in ───────────────────────────────────────────────────

def test_the_session_round_trips_and_is_private(fresh):
    from account import session_store
    session_store.save({"access_token": "a", "refresh_token": "r", "expires_at": 1.0,
                        "user": {"id": "u"}})
    assert session_store.load()["refresh_token"] == "r"
    path = session_store.folder() / "session.bin"
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    session_store.save_profile({"email": "a@b.co"})
    session_store.save_avatar(b"png")
    session_store.clear()
    assert session_store.load() is None
    assert not path.exists() and not session_store.avatar_file().exists()
    assert session_store.load_profile() == {}


def test_an_unreadable_session_is_forgotten_not_trusted(fresh):
    from account import session_store
    (session_store.folder() / "session.bin").write_bytes(b"garbage from another machine")
    assert session_store.load() is None
    assert not (session_store.folder() / "session.bin").exists()


def test_on_windows_the_session_is_encrypted_with_dpapi(fresh, monkeypatch):
    from account import session_store
    calls = []

    def fake_dpapi(data, protect):
        calls.append(protect)
        return bytes(b ^ 0x5A for b in data)
    monkeypatch.setattr(session_store.platform, "system", lambda: "Windows")
    monkeypatch.setattr(session_store, "_dpapi", fake_dpapi)
    session_store.save({"refresh_token": "secret-refresh-token"})
    blob = (session_store.folder() / "session.bin").read_bytes()
    assert blob.startswith(b"MIKE-DPAPI1\n") and b"secret-refresh-token" not in blob
    assert session_store.load()["refresh_token"] == "secret-refresh-token"
    assert calls == [True, False]


# ── errors a person can act on ──────────────────────────────────────────

class _Resp:
    def __init__(self, status, body):
        import json
        self.status_code = status
        self._body = body
        self.text = json.dumps(body)
        self.content = self.text.encode()

    def json(self):
        return self._body


@pytest.mark.parametrize("status,body,code,words", [
    (400, {"code": 400, "error_code": "invalid_credentials", "msg": "Invalid login credentials"},
     "invalid_credentials", "don't match"),
    (400, {"error": "invalid_grant", "error_description": "Invalid login credentials"},
     "invalid_credentials", "don't match"),
    (400, {"error": "invalid_grant", "error_description": "Invalid Refresh Token: Not Found"},
     "refresh_token_not_found", "signed out"),
    (422, {"error_code": "weak_password", "msg": "weak", "weak_password": {"reasons": ["pwned"]}},
     "weak_password", "data breach"),
    (429, {"error_code": "over_email_send_rate_limit",
           "msg": "For security purposes, you can only request this after 42 seconds."},
     "over_email_send_rate_limit", "42 seconds"),
    (403, {"error_code": "otp_expired", "msg": "Token has expired or is invalid"},
     "otp_expired", "code"),
    (500, {"code": 500, "error_code": "unexpected_failure", "msg": "db down"},
     "unexpected_failure", "Try again"),
])
def test_server_errors_become_sentences(status, body, code, words):
    from account.client import _error_from
    e = _error_from(_Resp(status, body))
    assert e.code == code
    assert words in e.message
    if code == "over_email_send_rate_limit":
        assert e.retry_after == 42
    if code == "refresh_token_not_found":
        assert e.session_ended


def test_no_connection_is_offline_not_an_account_problem():
    from account.client import NetworkError, SupabaseClient
    c = SupabaseClient("http://127.0.0.1:9", "k", timeout=2)
    with pytest.raises(NetworkError) as info:
        c.sign_in("a@b.co", "pw")
    assert "internet" in info.value.message and not info.value.session_ended


# ── Google: PKCE and the loopback ───────────────────────────────────────

def test_pkce_pair_is_s256():
    from account.loopback import pkce_pair
    verifier, challenge = pkce_pair()
    assert 43 <= len(verifier) <= 128
    expect = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
    assert challenge == expect.rstrip(b"=").decode()
    assert pkce_pair()[0] != verifier


def test_loopback_receives_the_code_and_answers_the_browser():
    import requests
    from account.loopback import Receiver
    rx = Receiver()
    assert rx.redirect_uri.startswith("http://127.0.0.1:") and rx.redirect_uri.endswith(
        "/auth/callback")
    assert requests.get(rx.redirect_uri.replace("/auth/callback", "/other"), timeout=5
                        ).status_code == 404
    page = requests.get(rx.redirect_uri + "?code=abc123", timeout=5)
    assert "signed in" in page.text
    assert rx.wait(2) == {"code": "abc123"}
    rx.close()


def test_loopback_reports_a_refusal_and_closes_promptly():
    import requests
    from account.loopback import Receiver
    rx = Receiver()
    page = requests.get(rx.redirect_uri + "?error=access_denied&error_description=Nope",
                        timeout=5)
    assert "didn't work" in page.text
    assert rx.wait(2)["error"] == "access_denied"
    rx.close()
    other = Receiver()
    t = time.time()
    other.close()
    assert other.wait(1) is None and time.time() - t < 1.5


def test_sign_in_urls_carry_the_challenge():
    from account.client import SupabaseClient
    url = SupabaseClient("https://x.supabase.co", "k").authorize_url(
        "google", "http://127.0.0.1:53682/auth/callback", "CHAL")
    assert url.startswith("https://x.supabase.co/auth/v1/authorize?provider=google")
    assert "code_challenge=CHAL" in url and "code_challenge_method=s256" in url
    assert "redirect_to=http%3A%2F%2F127.0.0.1%3A53682%2Fauth%2Fcallback" in url


# ── the sign-in card ────────────────────────────────────────────────────

def test_the_card_checks_what_it_can_before_asking_the_server(app, fresh, monkeypatch):
    _configure(monkeypatch)
    from ui.workspace.account_dialog import AuthDialog
    d = AuthDialog("create")
    d.show()
    d.cr_name.setText("Asha")
    d.cr_email.setText("not-an-email")
    d._create()
    assert "valid email" in d.p_create.error.text()
    d.cr_email.setText("asha@example.com")
    d.cr_password.setText("short")
    d._create()
    assert "8 characters" in d.p_create.error.text()
    d._go(d.p_new_password)
    d.np_password.setText("long-enough-1")
    d.np_confirm.setText("long-enough-2")
    d._save_new_password()
    assert "don't match" in d.p_new_password.error.text()
    assert not d._busy, "none of that reached the network"
    d.close()


def test_the_code_field_takes_digits_only(app, fresh, monkeypatch):
    _configure(monkeypatch)
    from ui.workspace.account_dialog import AuthDialog
    d = AuthDialog("sign_in")
    d._to_code("a@b.co", "email", resend="signup")
    d.code.setText("12a 3-4")
    d._code_edited(d.code.text())
    assert d.code.text() == "1234"
    assert not d.resend.isEnabled() and "60s" in d.resend.text(), \
        "resending waits, as Supabase requires"
    d.close()


def test_first_run_and_required_cards_offer_the_right_way_out(app, fresh, monkeypatch):
    from PySide6.QtWidgets import QPushButton
    _configure(monkeypatch)
    from ui.workspace.account_dialog import AuthDialog

    def labels(d):
        return [b.text() for b in d.findChildren(QPushButton)]
    plain = AuthDialog("sign_in")
    assert "Continue without an account" not in labels(plain)
    first = AuthDialog("create", first_run=True)
    assert "Continue without an account" in labels(first)
    skipped = []
    first.skipped.connect(lambda: skipped.append(1))
    first._skip()
    assert skipped == [1]
    gate = AuthDialog("sign_in", required=True)
    gate.show()
    assert "Quit Mike" in labels(gate)
    assert not gate._close.isVisible(), "a required sign-in can't just be closed"
    for d in (plain, gate):
        d.close()


def test_google_button_only_when_the_project_has_it(app, fresh, monkeypatch):
    from PySide6.QtWidgets import QPushButton
    from ui.workspace.account_dialog import AuthDialog
    _configure(monkeypatch)
    assert "Continue with Google" not in [b.text() for b in
                                          AuthDialog().findChildren(QPushButton)]
    _configure(monkeypatch, providers=["google"])
    assert "Continue with Google" in [b.text() for b in AuthDialog().findChildren(QPushButton)]


# ── starting Mike ───────────────────────────────────────────────────────

@pytest.fixture()
def windows():
    """Real MikeWindows, torn down after — a window left running keeps
    services like the IDE bridge's port, which the next Mike then can't take."""
    made = []
    yield made
    for w in made:
        w.close()
        w._teardown()


def _window(monkeypatch, windows):
    from ui.app import MikeWindow
    w = MikeWindow()
    windows.append(w)
    asked, quit_ = [], []
    monkeypatch.setattr(w, "_ask_account", lambda **kw: asked.append(kw) or False)
    monkeypatch.setattr(w, "_request_quit", lambda: quit_.append(1))
    return w, asked, quit_


def test_a_required_account_gates_mike(app, fresh, monkeypatch, windows):
    _configure(monkeypatch, required=True)
    w, asked, quit_ = _window(monkeypatch, windows)
    w._present()
    assert asked == [{"required": True}] and quit_ == [1]
    assert not w.isVisible(), "nothing of Mike shows until signed in"
    w.close()


def test_an_optional_account_is_offered_once_after_mike_appears(app, fresh, monkeypatch, windows):
    from config import preferences
    preferences.set_value("account_offered", False)
    _configure(monkeypatch)
    w, asked, quit_ = _window(monkeypatch, windows)
    w._present()
    assert w.isVisible() and not quit_
    _wait_for(lambda: asked)
    assert asked == [{"first_run": True}]
    assert preferences.get("account_offered") is True
    asked.clear()
    w._present()
    time.sleep(0.6)
    app.processEvents()
    assert asked == [], "offered once, not every launch"
    w.close()


def test_without_accounts_mike_starts_exactly_as_before(app, fresh, monkeypatch, windows):
    w, asked, quit_ = _window(monkeypatch, windows)
    w._present()
    time.sleep(0.6)
    app.processEvents()
    assert w.isVisible() and asked == [] and quit_ == []
    w.close()


def _wait_for(pred, timeout=5.0):
    from PySide6.QtWidgets import QApplication
    end = time.time() + timeout
    while time.time() < end:
        QApplication.instance().processEvents()
        if pred():
            return
        time.sleep(0.02)
    raise AssertionError("timed out")


# ── legal and data ──────────────────────────────────────────────────────

def test_the_privacy_policy_describes_accounts_exactly():
    from brain import legal
    text = " ".join(legal.load("privacy").split())
    assert "Your Mike account (optional)" in text
    assert "Supabase" in text
    for held in ("email address", "name", "photo"):
        assert held in text
    assert "never holds" in text and "conversations" in text
    assert "Delete account" in text


def test_the_terms_follow_whether_an_account_is_required(fresh, monkeypatch):
    from brain import legal
    assert "You don't need an account to use Mike." in legal.load("terms")
    _configure(monkeypatch, required=True)
    assert "You need a Mike account to use this copy of Mike." in legal.load("terms")


def test_accounts_changed_the_legal_version_so_people_are_asked_again():
    from config import settings
    assert settings.LEGAL_VERSION != "2026-09-25"


def test_export_includes_the_account_but_never_the_token(fresh, tmp_path):
    import json
    import zipfile
    from account import session_store
    from brain import data_export
    session_store.save({"access_token": "ACCESS-SECRET", "refresh_token": "REFRESH-SECRET",
                        "expires_at": 1.0, "user": {}})
    session_store.save_profile({"email": "asha@example.com", "display_name": "Asha",
                                "avatar_path": "u/avatar.png", "user_id": "u"})
    out = data_export.export_zip(tmp_path / "export.zip")
    with zipfile.ZipFile(out) as zf:
        everything = b"".join(zf.read(n) for n in zf.namelist())
        account = json.loads(zf.read("account.json"))
    assert account["email"] == "asha@example.com"
    assert b"SECRET" not in everything


def test_reset_signs_out_of_this_computer(fresh):
    from account import session_store
    from brain import data_export
    session_store.save({"access_token": "a", "refresh_token": "r", "expires_at": 1.0})
    data_export.reset_everything()
    assert session_store.load() is None


def test_a_problem_report_never_contains_the_sign_in(fresh, tmp_path):
    import zipfile
    from account import session_store
    from brain import support_bundle
    session_store.save({"access_token": "ACCESS-SECRET", "refresh_token": "REFRESH-SECRET",
                        "expires_at": 1.0})
    out = support_bundle.create(tmp_path / "report.zip")
    with zipfile.ZipFile(out) as zf:
        assert not [n for n in zf.namelist() if "account" in n or "session" in n]
        assert b"SECRET" not in b"".join(zf.read(n) for n in zf.namelist())


def test_signed_in_state_reaches_the_profile_row(app, fresh, monkeypatch):
    from account import session_store
    from account.client import Session
    from account.manager import manager
    from ui.workspace.sidebar import Sidebar
    _configure(monkeypatch)
    session_store.save(Session("a", "r", time.time() + 3600,
                               {"id": "u", "email": "asha@example.com"}).to_dict())
    session_store.save_profile({"email": "asha@example.com", "display_name": "Asha"})
    m = manager()
    m.restore()  # the network is unreachable: stays signed in, from the cache
    assert m.signed_in() and m.display_name() == "Asha"
    bar = Sidebar()
    bar.refresh_profile()
    assert bar.profile._name == "Asha" and bar.profile._subtitle == "asha@example.com"
    _wait_for(lambda: m.offline)
    assert m.signed_in(), "offline is not signed out"
    m._refresh_timer.stop()
