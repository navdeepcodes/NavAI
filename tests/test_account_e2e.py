"""Mike accounts against a real Supabase — Auth, Postgres with the shipped
migration, PostgREST, Storage — running locally (tests/supabase_stack.py).

Every flow a person can take is driven through the same AccountManager the
app uses, including reading the actual 6-digit codes out of the emails Auth
sends with Mike's templates. Also proves the security the migration promises:
one account can't read or change another's profile or photo, signing out
revokes the saved session on the server, and deleting an account removes it.

Skipped when Docker isn't available. MIKE_SB_KEEP=1 leaves the stack running
between runs.
"""
from __future__ import annotations

import os
import sys
import time
import uuid

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import _isolate  # noqa: F401,E402
from tests import supabase_stack as sb  # noqa: E402

pytestmark = pytest.mark.skipif(not sb.docker_available(), reason="needs Docker")


@pytest.fixture(scope="module")
def stack():
    cfg = sb.up(verbose=False)
    yield cfg
    if not os.environ.get("MIKE_SB_KEEP"):
        sb.down()


@pytest.fixture()
def mgr(stack, monkeypatch):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)
    from config import preferences, settings
    monkeypatch.setattr(settings, "SUPABASE_URL", stack["url"])
    monkeypatch.setattr(settings, "SUPABASE_ANON_KEY", stack["anon_key"])
    from account import manager as m
    from account import session_store
    session_store.clear()
    preferences.set_value("profile_name", "")
    m.reset_for_tests()
    yield m.manager()
    m.manager().cancel_sign_in()
    m.reset_for_tests()


def _wait(pred, timeout=25.0):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if pred():
            return
        time.sleep(0.02)
    raise AssertionError("timed out")


def call(method, *args, **kw):
    """Run an AccountManager operation to completion: ("ok", result) or ("err", error)."""
    box: dict = {}
    method(*args, ok=lambda *r: box.setdefault("ok", r[0] if r else None),
           err=lambda e: box.setdefault("err", e), **kw)
    _wait(lambda: box)
    return ("ok", box["ok"]) if "ok" in box else ("err", box["err"])


def ok(method, *args, **kw):
    kind, value = call(method, *args, **kw)
    assert kind == "ok", f"{method.__name__} failed: {getattr(value, 'code', '')} {value}"
    return value


def _email(tag: str) -> str:
    return f"{tag}-{uuid.uuid4().hex[:8]}@example.com"


def _create_account(mgr, name="Asha", password="correct-horse-9"):
    email = _email(name.lower())
    t = time.time()
    assert ok(mgr.sign_up, email, password, name) == "confirm"
    assert not mgr.signed_in()
    ok(mgr.verify_code, email, sb.latest_code(email, after=t), "email")
    assert mgr.signed_in()
    return email, password


def _admin():
    from account.client import SupabaseClient
    return SupabaseClient(sb.URL, sb.SERVICE_KEY)


# ── creating an account and staying signed in ───────────────────────────

def test_sign_up_confirms_by_code_and_the_profile_takes_the_name(mgr):
    from account import session_store
    from config import preferences

    email, _pw = _create_account(mgr, "Asha")
    assert mgr.email() == email
    assert mgr.display_name() == "Asha", "the sign-up name becomes the account's profile"
    assert preferences.get("profile_name") == "Asha", "and the name Mike calls you"
    assert "Your Mike code" in sb.mail_subjects(email), "sent with Mike's own template"
    saved = session_store.load()
    assert saved and saved["refresh_token"], "the sign-in is kept for the next launch"


def test_a_saved_sign_in_is_restored_on_the_next_launch(mgr):
    from account import manager as m

    email, _pw = _create_account(mgr, "Ravi")
    m.reset_for_tests()
    again = m.manager()
    again.restore()
    assert again.signed_in(), "signed in straight away, from the saved session"
    _wait(lambda: again.user.get("id"))
    assert again.email() == email


def test_an_account_without_a_name_takes_the_one_mike_already_uses(mgr):
    from config import preferences
    preferences.set_value("profile_name", "Navdeep")
    email = _email("noname")
    t = time.time()
    assert ok(mgr.sign_up, email, "correct-horse-9", "") == "confirm"
    ok(mgr.verify_code, email, sb.latest_code(email, after=t), "email")
    assert mgr.display_name() == "Navdeep"


def test_wrong_codes_and_passwords_are_explained(mgr):
    email, pw = _create_account(mgr)
    mgr.sign_out()
    kind, e = call(mgr.sign_in, email, "not-the-password")
    assert kind == "err" and e.code == "invalid_credentials"
    assert "don't match" in e.message
    kind, e = call(mgr.verify_code, email, "000000", "email")
    assert kind == "err" and e.code == "otp_expired"
    kind, e = call(mgr.sign_up, email, pw, "Again")
    assert kind == "err" and e.code == "user_already_exists"
    kind, e = call(mgr.sign_up, _email("weak"), "123", "Weak")
    assert kind == "err" and e.code == "weak_password"


def test_an_unconfirmed_account_is_asked_for_its_code(mgr):
    email = _email("pending")
    assert ok(mgr.sign_up, email, "correct-horse-9", "Pending") == "confirm"
    kind, e = call(mgr.sign_in, email, "correct-horse-9")
    assert kind == "err" and e.code == "email_not_confirmed"
    time.sleep(1.2)  # the stack allows one email a second per address
    t = time.time()
    ok(mgr.resend_signup, email)
    ok(mgr.verify_code, email, sb.latest_code(email, after=t), "email")
    assert mgr.signed_in()


# ── other ways in ───────────────────────────────────────────────────────

def test_sign_in_with_an_emailed_code(mgr):
    email, _pw = _create_account(mgr)
    mgr.sign_out()
    t = time.time()
    ok(mgr.send_code, email)
    ok(mgr.verify_code, email, sb.latest_code(email, after=t), "email")
    assert mgr.signed_in() and mgr.email() == email


def test_a_code_sign_in_for_an_unknown_email_says_to_create_an_account(mgr):
    kind, e = call(mgr.send_code, _email("nobody"))
    assert kind == "err" and e.code == "otp_disabled"


def test_forgotten_password_reset_by_code(mgr):
    email, _pw = _create_account(mgr)
    mgr.sign_out()
    t = time.time()
    ok(mgr.send_recovery, email)
    ok(mgr.verify_code, email, sb.latest_code(email, after=t), "recovery")
    assert mgr.signed_in()
    ok(mgr.set_password, "a-brand-new-password-4")
    mgr.sign_out()
    ok(mgr.sign_in, email, "a-brand-new-password-4")
    assert mgr.signed_in()


def test_google_sign_in_starts_a_real_pkce_flow_and_handles_the_return(mgr, monkeypatch):
    import requests
    from PySide6.QtGui import QDesktopServices

    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString()))
    box: dict = {}
    url = mgr.sign_in_with("google", ok=lambda: box.setdefault("ok", 1),
                           err=lambda e: box.setdefault("err", e))
    assert opened == [url]
    # Supabase sends the browser on to Google, carrying a PKCE flow it created.
    r = requests.get(url, allow_redirects=False, timeout=10)
    assert r.status_code in (302, 303), r.text[:300]
    assert r.headers["Location"].startswith("https://accounts.google.com/")
    # The browser comes back to Mike's listener. A code that isn't real is
    # refused by Supabase, and the person is told — nothing hangs.
    redirect = [q for q in url.split("&") if q.startswith("redirect_to=")][0]
    from urllib.parse import unquote
    back = unquote(redirect.split("=", 1)[1])
    page = requests.get(back + "?code=not-a-real-code", timeout=10)
    assert "close this tab" in page.text
    _wait(lambda: box)
    assert "err" in box and not mgr.signed_in()


def test_google_sign_in_can_be_cancelled(mgr, monkeypatch):
    from PySide6.QtGui import QDesktopServices
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: True)
    box: dict = {}
    mgr.sign_in_with("google", ok=lambda: box.setdefault("ok", 1),
                     err=lambda e: box.setdefault("err", e))
    mgr.cancel_sign_in()
    time.sleep(1.2)
    from PySide6.QtWidgets import QApplication
    QApplication.instance().processEvents()
    assert not box, "a cancelled sign-in reports nothing"


# ── the profile ─────────────────────────────────────────────────────────

def _png(colour: str) -> bytes:
    import tempfile
    from PySide6.QtGui import QColor, QImage
    from account.manager import avatar_png
    img = QImage(640, 480, QImage.Format_RGB32)
    img.fill(QColor(colour))
    path = os.path.join(tempfile.mkdtemp(), "photo.jpg")
    img.save(path, "JPEG")
    return avatar_png(path)


def test_name_and_photo_sync_and_stay_private(mgr):
    from account import session_store
    from account.client import AccountError, SupabaseClient
    from PySide6.QtGui import QImage

    email_a, pw_a = _create_account(mgr, "Asha")
    ok(mgr.update_name, "Asha K")
    assert mgr.display_name() == "Asha K"
    png = _png("#E0A050")
    assert QImage.fromData(png).size().width() == 256, "cropped square and scaled"
    ok(mgr.set_avatar, png)
    assert mgr.avatar_file() and mgr.avatar_file().read_bytes() == png
    uid_a = mgr.user["id"]
    path_a = mgr.profile["avatar_path"]
    assert path_a == f"{uid_a}/avatar.png"

    # The server has it: a fresh sign-in on "another computer" gets both.
    mgr.sign_out()
    assert mgr.avatar_file() is None and not session_store.avatar_file().exists()
    ok(mgr.sign_in, email_a, pw_a)
    assert mgr.display_name() == "Asha K"
    assert mgr.avatar_file().read_bytes() == png

    # Someone else, signed in, can't read or change any of it.
    client = SupabaseClient(sb.URL, sb.ANON_KEY)
    email_b = _email("other")
    t = time.time()
    client.sign_up(email_b, "correct-horse-9", "Other")
    other = client.verify(email_b, sb.latest_code(email_b, after=t), "email")
    assert client.get_profile(other.access_token, uid_a) is None
    with pytest.raises(AccountError):
        client.save_profile(other.access_token, uid_a, display_name="Hacked")
    with pytest.raises(AccountError):
        client.download_avatar(other.access_token, path_a)
    with pytest.raises(AccountError):
        client.upload_avatar(other.access_token, path_a, b"not yours")
    try:
        client.remove_avatar(other.access_token, path_a)
    except AccountError:
        pass  # refused outright ("Access denied") — or quietly, as a no-op
    assert client.download_avatar(mgr._access(), path_a) == png, "the photo is untouched"
    # And nobody signed out can read profiles at all: refused, or nothing.
    try:
        rows = client._request("GET", "/rest/v1/profiles", params={"select": "*"}).json()
    except AccountError:
        rows = []
    assert rows == []
    ok(mgr.remove_avatar)
    assert mgr.avatar_file() is None and mgr.profile["avatar_path"] == ""


# ── security of the session ─────────────────────────────────────────────

def test_an_expired_access_token_is_refreshed_transparently(mgr):
    from account import session_store
    _create_account(mgr)
    old_refresh = mgr._session.refresh_token
    mgr._session.expires_at = time.time() - 10
    ok(mgr.update_name, "Refreshed")
    assert mgr._session.refresh_token != old_refresh, "refresh tokens rotate"
    assert session_store.load()["refresh_token"] == mgr._session.refresh_token, \
        "and the new one is saved at once"


def test_signing_out_revokes_the_session_on_the_server(mgr):
    from account.client import AccountError, SupabaseClient
    _create_account(mgr)
    refresh = mgr._session.refresh_token
    mgr.sign_out()
    assert not mgr.signed_in()
    client = SupabaseClient(sb.URL, sb.ANON_KEY)
    deadline = time.time() + 10
    while True:
        try:
            client.refresh(refresh)
        except AccountError as exc:
            assert exc.session_ended
            break
        assert time.time() < deadline, "a signed-out session must stop working"
        time.sleep(0.5)


def test_a_session_revoked_elsewhere_signs_out_with_a_notice(mgr):
    from account import manager as m
    email, pw = _create_account(mgr)
    # Signing out everywhere from another device revokes every refresh token.
    from account.client import SupabaseClient
    client = SupabaseClient(sb.URL, sb.ANON_KEY)
    other = client.sign_in(email, pw)
    client._request("POST", "/auth/v1/logout", access=other.access_token,
                    params={"scope": "global"})
    m.reset_for_tests()
    again = m.manager()
    notices = []
    again.notice.connect(notices.append)
    again._session = None
    again.restore()
    again._session.expires_at = time.time() - 10  # force the refresh
    _wait(lambda: not again.signed_in())
    assert notices and "signed out" in notices[0]


# ── changing sign-in details ────────────────────────────────────────────

def test_changing_email_needs_both_addresses_confirmed(mgr):
    old, _pw = _create_account(mgr)
    new = _email("moved")
    t = time.time()
    ok(mgr.change_email, new)
    assert mgr.pending_email() == new
    complete = ok(mgr.confirm_email_change, new, sb.latest_code(new, after=t))
    if not complete:
        complete = ok(mgr.confirm_email_change, old, sb.latest_code(old, after=t))
    assert complete
    assert mgr.email() == new and not mgr.pending_email()


def test_password_change_with_a_reauthentication_code(mgr):
    email, _pw = _create_account(mgr)
    t = time.time()
    ok(mgr.request_reauthentication)
    ok(mgr.set_password, "another-password-7", sb.latest_code(email, after=t))
    mgr.sign_out()
    ok(mgr.sign_in, email, "another-password-7")


# ── leaving ─────────────────────────────────────────────────────────────

def test_deleting_the_account_removes_it_everywhere(mgr):
    from account import session_store
    from config import preferences
    email, pw = _create_account(mgr, "Leaving")
    ok(mgr.set_avatar, _png("#3060A0"))
    uid = mgr.user["id"]
    path = mgr.profile["avatar_path"]
    ok(mgr.delete_account)
    assert not mgr.signed_in() and session_store.load() is None
    kind, e = call(mgr.sign_in, email, pw)
    assert kind == "err" and e.code == "invalid_credentials"
    admin = _admin()
    rows = admin._request("GET", "/rest/v1/profiles", access=sb.SERVICE_KEY,
                          params={"id": f"eq.{uid}", "select": "id"}).json()
    assert rows == [], "the profile is gone"
    objects = admin._request("POST", "/storage/v1/object/list/avatars", access=sb.SERVICE_KEY,
                             json={"prefix": uid, "limit": 10}).json()
    assert not [o for o in objects if o.get("name") == "avatar.png"], "and the photo"
    assert preferences.get("profile_name") == "Leaving", \
        "what's on this computer is untouched"
    assert path


# ── through the interface ───────────────────────────────────────────────

def test_creating_an_account_through_the_card(mgr):
    from PySide6.QtWidgets import QDialog
    from ui.workspace.account_dialog import AuthDialog
    d = AuthDialog("create")
    d.show()
    email = _email("card")
    d.cr_name.setText("Card Person")
    d.cr_email.setText(email)
    d.cr_password.setText("correct-horse-9")
    t = time.time()
    d._create()
    _wait(lambda: d._page() is d.p_code)
    assert email in d.p_code.lead.text()
    code = sb.latest_code(email, after=t)
    d.code.setText(code)
    d._code_edited(code)  # six digits: submits by itself
    _wait(lambda: d.result() == QDialog.Accepted)
    assert mgr.signed_in() and mgr.display_name() == "Card Person"


def test_resetting_a_password_through_the_card(mgr):
    from PySide6.QtWidgets import QDialog
    from ui.workspace.account_dialog import AuthDialog
    email, _pw = _create_account(mgr)
    mgr.sign_out()
    d = AuthDialog("sign_in")
    d.show()
    d.si_email.setText(email)
    d.si_password.setText("wrong-password-1")
    d._sign_in()
    _wait(lambda: d.p_sign_in.error.isVisible())
    assert "don't match" in d.p_sign_in.error.text()
    d._go(d.p_forgot, email=email)
    assert d.fg_email.text() == email, "the email carries over"
    time.sleep(1.1)
    t = time.time()
    d._forgot()
    _wait(lambda: d._page() is d.p_code)
    d.code.setText(sb.latest_code(email, after=t))
    d._submit_code()
    _wait(lambda: d._page() is d.p_new_password)
    d.np_password.setText("reset-by-code-5")
    d.np_confirm.setText("reset-by-code-5")
    d._save_new_password()
    _wait(lambda: d.result() == QDialog.Accepted)
    mgr.sign_out()
    ok(mgr.sign_in, email, "reset-by-code-5")


def test_the_account_tab_edits_the_profile_and_signs_out(mgr):
    from PySide6.QtWidgets import QLabel
    from ui.workspace.account_tab import AccountTab
    from config import preferences
    _create_account(mgr, "Tabby")
    tab = AccountTab()
    assert tab._name.text() == "Tabby"
    tab._name.setText("Tabitha")
    tab._save_name()
    _wait(lambda: mgr.display_name() == "Tabitha")
    assert preferences.get("profile_name") == "Tabitha"
    tab._sign_out()
    assert not mgr.signed_in()
    _wait(lambda: any(lbl.text() == "Sign in to Mike" and lbl.isVisibleTo(tab)
                      for lbl in tab.findChildren(QLabel)))


def test_a_name_changed_offline_is_sent_when_back_online(mgr, monkeypatch):
    from account import manager as m
    from account.client import SupabaseClient
    _create_account(mgr, "Before")
    # Offline: the account service can't be reached.
    real = mgr._client()
    monkeypatch.setattr(mgr, "_client", lambda: SupabaseClient("http://127.0.0.1:9", "k", 2))
    kind, e = call(mgr.update_name, "Renamed Offline")
    assert kind == "err" and e.code == "network"
    assert mgr.display_name() == "Renamed Offline", "kept on this computer meanwhile"
    # Next launch, online again: the offline rename wins over the server's older name.
    monkeypatch.setattr(mgr, "_client", lambda: real)
    m.reset_for_tests()
    again = m.manager()
    again.restore()
    _wait(lambda: again.user.get("id") and not again.profile.get("pending_name"))
    assert again.display_name() == "Renamed Offline"
    uid = again.user["id"]
    assert real.get_profile(again._access(), uid)["display_name"] == "Renamed Offline"
