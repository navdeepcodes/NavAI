"""The account, as the app sees it: who's signed in, and everything you can do.

One AccountManager per app (manager()). Every network call runs on a worker
thread and reports back on the GUI thread through callbacks, so the interface
never waits on the internet. The rules it keeps:

- Signed in stays signed in. The session is refreshed shortly before it
  expires and whenever a call finds it stale; a refresh that can't reach the
  server leaves you signed in and offline, and tries again with backoff.
- Only the server can sign you out: a refresh token it rejects (revoked,
  expired, account deleted) ends the session, and `notice` says so.
- The name Mike calls you is one name. Signing in adopts the account's name;
  an account without one takes the name you'd already given Mike.
- Conversations, memory, files and activity are never sent. Only the email,
  name and photo live in the account.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal, Slot

from account import config, session_store
from account.client import AccountError, NetworkError, Session, SupabaseClient
from logs.logger import logger

Ok = Callable[..., None] | None
Err = Callable[[AccountError], None] | None

AVATAR_SIZE = 256


class _Bridge(QObject):
    """Carries a worker thread's result back to the GUI thread: the bridge
    lives on the GUI thread, so its queued slot runs there."""
    call = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.call.connect(self._run, Qt.QueuedConnection)

    @Slot(object)
    def _run(self, fn) -> None:
        fn()


class AccountManager(QObject):
    #: The account's state changed: signed in or out, profile, photo, offline.
    changed = Signal()
    #: Something the person should be told outside of any dialog
    #: ("You've been signed out. Sign in again.").
    notice = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._bridge = _Bridge()
        self._lock = threading.RLock()
        self._session: Session | None = None
        self._client_cache: tuple[tuple[str, str], SupabaseClient] | None = None
        self._oauth = None
        self.user: dict = {}
        self.profile: dict = {}
        self.offline = False
        self.status = "signed_out" if config.configured() else "unavailable"
        self._retry_s = 30
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._refresh_now)

    # ── state ────────────────────────────────────────────────────────────
    def available(self) -> bool:
        return config.configured()

    def signed_in(self) -> bool:
        return self.status == "signed_in"

    def email(self) -> str:
        return str(self.user.get("email") or self.profile.get("email") or "")

    def pending_email(self) -> str:
        """The new address of an email change waiting to be confirmed."""
        return str(self.user.get("new_email") or "")

    def display_name(self) -> str:
        return str(self.profile.get("display_name") or "").strip()

    def avatar_file(self) -> Path | None:
        path = session_store.avatar_file()
        return path if self.signed_in() and path.exists() else None

    def providers(self) -> list[str]:
        meta = self.user.get("app_metadata") or {}
        return [str(p) for p in (meta.get("providers") or [meta.get("provider") or ""]) if p]

    def has_password(self) -> bool:
        return "email" in self.providers()

    # ── plumbing ─────────────────────────────────────────────────────────
    def _client(self) -> SupabaseClient:
        key = (config.url(), config.anon_key())
        if self._client_cache is None or self._client_cache[0] != key:
            self._client_cache = (key, SupabaseClient(*key))
        return self._client_cache[1]

    def _post(self, fn) -> None:
        self._bridge.call.emit(fn)

    def _run(self, work, ok: Ok = None, err: Err = None) -> None:
        def task():
            # Values are bound as defaults: `except ... as exc` unbinds exc when
            # the block ends, long before the GUI thread runs the callback.
            try:
                result = work()
            except AccountError as exc:
                self._post(lambda e=exc: self._failed(e, err))
            except Exception:
                logger.exception("Account operation failed.")
                failure = AccountError("Something went wrong. Try again in a moment.",
                                       code="unexpected")
                self._post(lambda e=failure: self._failed(e, err))
            else:
                self._post(lambda r=result: self._succeeded(r, ok))
        threading.Thread(target=task, daemon=True, name="mike-account").start()

    def _succeeded(self, result, ok: Ok) -> None:
        if self.offline:
            self.offline = False
            self._retry_s = 30
            self.changed.emit()
        if ok:
            ok(result)

    def _failed(self, exc: AccountError, err: Err) -> None:
        if exc.session_ended and self._session is not None:
            self._end_session("You've been signed out of your Mike account. Sign in again.")
        elif isinstance(exc, NetworkError) and self.signed_in() and not self.offline:
            self.offline = True
            self.changed.emit()
        if err:
            err(exc)

    def _store(self, session: Session) -> None:
        """Keep a new session (any thread): memory, disk, refresh timer."""
        with self._lock:
            if not session.user and self._session is not None:
                session.user = self._session.user
            self._session = session
            session_store.save(session.to_dict())
        self._post(self._schedule_refresh)

    def _access(self, force: bool = False) -> str:
        """A valid access token (worker thread), refreshing when it's near expiry."""
        with self._lock:
            s = self._session
            if s is None:
                raise AccountError("You're not signed in.", code="no_authorization")
            if not force and s.expires_in() > 60:
                return s.access_token
            fresh = self._client().refresh(s.refresh_token)
            self._store(fresh)
            return fresh.access_token

    def _authed(self, fn):
        """fn(access) with a fresh token — retried once if the token was stale."""
        try:
            return fn(self._access())
        except AccountError as exc:
            if exc.status == 401 or exc.code == "bad_jwt":
                return fn(self._access(force=True))
            raise

    def _schedule_refresh(self) -> None:
        s = self._session
        if s is None:
            self._refresh_timer.stop()
            return
        self._refresh_timer.start(int(max(5.0, s.expires_in() - 120) * 1000))

    def _refresh_now(self) -> None:
        if self._session is None:
            return

        def retry(exc: AccountError) -> None:
            if isinstance(exc, NetworkError):
                self._refresh_timer.start(self._retry_s * 1000)
                self._retry_s = min(self._retry_s * 2, 300)
        self._run(lambda: self._access(force=True), err=retry)

    # ── starting, adopting and ending sessions ──────────────────────────
    def restore(self) -> None:
        """At startup: pick the saved sign-in back up, then bring it up to date."""
        if not config.configured():
            self.status = "unavailable"
            return
        data = session_store.load()
        if not data:
            self.status = "signed_out"
            return
        try:
            self._session = Session.from_dict(data)
        except Exception:
            session_store.clear()
            self.status = "signed_out"
            return
        self.user = self._session.user
        self.profile = session_store.load_profile()
        self.status = "signed_in"
        self.changed.emit()
        self._schedule_refresh()
        local = self._local_name()

        def work():
            user = self._authed(self._client().get_user)
            with self._lock:
                if self._session is not None:
                    self._session.user = user
                    session_store.save(self._session.to_dict())
            return user, self._sync_profile(user, local)

        def failed(exc: AccountError) -> None:
            if isinstance(exc, NetworkError):
                self._refresh_timer.start(self._retry_s * 1000)
        self._run(work, ok=lambda r: self._adopted(*r), err=failed)

    def _adopt(self, session: Session, local: str) -> tuple[dict, dict]:
        """Worker thread: keep a brand-new session and fetch its profile."""
        self._store(session)
        user = session.user or self._client().get_user(session.access_token)
        return user, self._sync_profile(user, local)

    def _adopted(self, user: dict, profile: dict) -> None:
        if self._session is None:
            return  # signed out while this was in flight
        self.user = user
        self.profile = profile
        self.status = "signed_in"
        name = profile.get("display_name") or ""
        if name:
            from config import preferences
            preferences.set_value("profile_name", name)
        self.changed.emit()

    def _sync_profile(self, user: dict, local_name: str) -> dict:
        """Worker thread: the account's profile, its photo cached, the name reconciled."""
        client = self._client()
        uid = str(user.get("id") or "")
        cached = session_store.load_profile()
        pending = cached.get("pending_name")
        if pending is not None and cached.get("user_id") == uid:
            # Renamed while offline: that's the newest name, so it goes up first.
            profile = self._authed(lambda a: client.save_profile(
                a, uid, display_name=pending or None))
        else:
            profile = self._authed(lambda a: client.get_profile(a, uid)) or {}
        if not profile.get("display_name") and local_name:
            profile = self._authed(lambda a: client.save_profile(a, uid, display_name=local_name))
        path = profile.get("avatar_path") or ""
        if path:
            fresh = (cached.get("avatar_path") == path
                     and cached.get("updated_at") == profile.get("updated_at")
                     and session_store.avatar_file().exists())
            if not fresh:
                try:
                    session_store.save_avatar(self._authed(lambda a: client.download_avatar(a, path)))
                except AccountError as exc:
                    if isinstance(exc, NetworkError):
                        raise
                    session_store.save_avatar(None)
        else:
            session_store.save_avatar(None)
        out = {"user_id": uid, "email": user.get("email") or "",
               "display_name": profile.get("display_name") or "",
               "avatar_path": path, "updated_at": profile.get("updated_at") or ""}
        session_store.save_profile(out)
        return out

    def _end_session(self, reason: str | None) -> None:
        with self._lock:
            self._session = None
            session_store.clear()
        self._refresh_timer.stop()
        self.user, self.profile = {}, {}
        self.offline = False
        self.status = "signed_out" if config.configured() else "unavailable"
        self.changed.emit()
        if reason:
            self.notice.emit(reason)

    @staticmethod
    def _local_name() -> str:
        try:
            from config import preferences
            return str(preferences.get("profile_name", "") or "").strip()
        except Exception:
            return ""

    # ── signing in ───────────────────────────────────────────────────────
    def sign_in(self, email: str, password: str, ok: Ok = None, err: Err = None) -> None:
        local = self._local_name()
        self._run(lambda: self._adopt(self._client().sign_in(email.strip(), password), local),
                  ok=lambda r: (self._adopted(*r), ok and ok()), err=err)

    def sign_up(self, email: str, password: str, name: str,
                ok: Ok = None, err: Err = None) -> None:
        """ok("signed_in") straight away, or ok("confirm") — a code was emailed."""
        local = name.strip() or self._local_name()

        def work():
            session, _user = self._client().sign_up(email.strip(), password, local)
            if session is None:
                return "confirm", None
            return "signed_in", self._adopt(session, local)

        def done(result):
            state, adopted = result
            if adopted:
                self._adopted(*adopted)
            if ok:
                ok(state)
        self._run(work, ok=done, err=err)

    def send_code(self, email: str, ok: Ok = None, err: Err = None) -> None:
        """Email a one-time code to sign in without a password."""
        self._run(lambda: self._client().send_code(email.strip()), ok=lambda _r: ok and ok(),
                  err=err)

    def resend_signup(self, email: str, ok: Ok = None, err: Err = None) -> None:
        self._run(lambda: self._client().resend("signup", email.strip()),
                  ok=lambda _r: ok and ok(), err=err)

    def send_recovery(self, email: str, ok: Ok = None, err: Err = None) -> None:
        self._run(lambda: self._client().send_recovery(email.strip()),
                  ok=lambda _r: ok and ok(), err=err)

    def verify_code(self, email: str, code: str, kind: str = "email",
                    ok: Ok = None, err: Err = None) -> None:
        """kind "email" (sign-up / sign-in code) or "recovery": signs you in."""
        local = self._local_name()

        def work():
            session = self._client().verify(email.strip(), code, kind)
            if session is None:
                raise AccountError("That code couldn't be used. Ask for a new one.",
                                   code="otp_expired")
            return self._adopt(session, local)
        self._run(work, ok=lambda r: (self._adopted(*r), ok and ok()), err=err)

    def sign_in_with(self, provider: str, ok: Ok = None, err: Err = None) -> str:
        """Open the provider's sign-in page in the browser; ok() once signed in.
        Returns the page's URL, so it can be offered again if the browser
        didn't open."""
        from PySide6.QtGui import QDesktopServices

        from account.loopback import Receiver, pkce_pair

        self.cancel_sign_in()
        verifier, challenge = pkce_pair()
        receiver = Receiver()
        self._oauth = receiver
        url = self._client().authorize_url(provider, receiver.redirect_uri, challenge)
        local = self._local_name()

        def work():
            query = receiver.wait(300)
            receiver.close()
            if self._oauth is not receiver:
                raise AccountError("", code="cancelled")
            if not query:
                raise AccountError("Signing in took too long. Try again.", code="timeout")
            if "error" in query:
                raise AccountError(
                    query.get("error_description") or "Signing in was cancelled.",
                    code=query.get("error_code") or query["error"])
            return self._adopt(self._client().exchange_code(query["code"], verifier), local)

        def done(r):
            self._oauth = None
            self._adopted(*r)
            if ok:
                ok()

        def failed(exc: AccountError) -> None:
            if exc.code != "cancelled" and err:
                err(exc)
        self._run(work, ok=done, err=failed)
        QDesktopServices.openUrl(QUrl(url))
        return url

    def cancel_sign_in(self) -> None:
        receiver, self._oauth = self._oauth, None
        if receiver is not None:
            receiver.close()

    # ── signed in ────────────────────────────────────────────────────────
    def sign_out(self, ok: Ok = None) -> None:
        """Sign out of this computer. Local at once; the server is told if it
        can be reached (so the saved sign-in is revoked, not just forgotten)."""
        s = self._session
        self.cancel_sign_in()
        self._end_session(None)
        if s is not None:
            def revoke():
                try:
                    self._client().sign_out(s.access_token)
                except AccountError:
                    pass
            threading.Thread(target=revoke, daemon=True).start()
        if ok:
            ok()

    def update_name(self, name: str, ok: Ok = None, err: Err = None) -> None:
        name = name.strip()[:80]

        def work():
            uid = self._session.user_id if self._session else ""
            return self._authed(lambda a: self._client().save_profile(
                a, uid, display_name=name or None))

        def done(row):
            self.profile = {**self.profile, "display_name": row.get("display_name") or "",
                            "updated_at": row.get("updated_at") or ""}
            self.profile.pop("pending_name", None)
            session_store.save_profile(self.profile)
            self.changed.emit()
            if ok:
                ok()

        def failed(exc: AccountError) -> None:
            if isinstance(exc, NetworkError):
                # Keep it, and send it the next time the account syncs.
                self.profile = {**self.profile, "display_name": name, "pending_name": name}
                session_store.save_profile(self.profile)
                self.changed.emit()
            if err:
                err(exc)
        self._run(work, ok=done, err=failed)

    def set_avatar(self, png: bytes, ok: Ok = None, err: Err = None) -> None:
        """Upload a new photo (PNG bytes, already square — see avatar_png)."""
        def work():
            uid = self._session.user_id if self._session else ""
            path = f"{uid}/avatar.png"
            client = self._client()
            self._authed(lambda a: client.upload_avatar(a, path, png, "image/png"))
            row = self._authed(lambda a: client.save_profile(a, uid, avatar_path=path))
            session_store.save_avatar(png)
            return row

        def done(row):
            self.profile = {**self.profile, "avatar_path": row.get("avatar_path") or "",
                            "updated_at": row.get("updated_at") or ""}
            session_store.save_profile(self.profile)
            self.changed.emit()
            if ok:
                ok()
        self._run(work, ok=done, err=err)

    def remove_avatar(self, ok: Ok = None, err: Err = None) -> None:
        path = str(self.profile.get("avatar_path") or "")

        def work():
            uid = self._session.user_id if self._session else ""
            client = self._client()
            if path:
                self._authed(lambda a: client.remove_avatar(a, path))
            row = self._authed(lambda a: client.save_profile(a, uid, avatar_path=None))
            session_store.save_avatar(None)
            return row

        def done(row):
            self.profile = {**self.profile, "avatar_path": "",
                            "updated_at": row.get("updated_at") or ""}
            session_store.save_profile(self.profile)
            self.changed.emit()
            if ok:
                ok()
        self._run(work, ok=done, err=err)

    def change_email(self, new_email: str, ok: Ok = None, err: Err = None) -> None:
        """Starts an email change: codes go to the new address (and, if the
        project asks for both, the current one). Finish with confirm_email_change."""
        def done(user):
            self.user = {**self.user, **user}
            self.changed.emit()
            if ok:
                ok()
        self._run(lambda: self._authed(lambda a: self._client().update_user(
            a, email=new_email.strip())), ok=done, err=err)

    def confirm_email_change(self, email: str, code: str, ok: Ok = None, err: Err = None) -> None:
        """ok(True) when the change is complete; ok(False) when the code sent to
        the other address is still needed."""
        def work():
            session = self._client().verify(email.strip(), code, "email_change")
            if session is not None:
                self._store(session)
            user = self._authed(self._client().get_user)
            return session is not None or not user.get("new_email"), user

        def done(result):
            complete, user = result
            self.user = user
            if self._session is not None:
                self._session.user = user
            self.profile = {**self.profile, "email": user.get("email") or ""}
            session_store.save_profile(self.profile)
            self.changed.emit()
            if ok:
                ok(complete)
        self._run(work, ok=done, err=err)

    def request_reauthentication(self, ok: Ok = None, err: Err = None) -> None:
        self._run(lambda: self._authed(self._client().reauthenticate),
                  ok=lambda _r: ok and ok(), err=err)

    def set_password(self, password: str, nonce: str | None = None,
                     ok: Ok = None, err: Err = None) -> None:
        def done(user):
            self.user = {**self.user, **user}
            self.changed.emit()
            if ok:
                ok()
        self._run(lambda: self._authed(lambda a: self._client().update_user(
            a, password=password, nonce=nonce)), ok=done, err=err)

    def delete_account(self, ok: Ok = None, err: Err = None) -> None:
        """Permanently delete the account, its profile and photo. What's on
        this computer (conversations, memory, files) is not touched."""
        path = str(self.profile.get("avatar_path") or "")

        def work():
            client = self._client()
            if path:
                try:
                    self._authed(lambda a: client.remove_avatar(a, path))
                except AccountError as exc:
                    if isinstance(exc, NetworkError):
                        raise
                    logger.info("Photo already gone before account deletion (%s).", exc.code)
            self._authed(client.delete_account)

        def done(_r):
            self._end_session(None)
            if ok:
                ok()
        self._run(work, ok=done, err=err)

    def forget_locally(self) -> None:
        """Used by "Start over": forget the sign-in without contacting anyone."""
        self.cancel_sign_in()
        self._end_session(None)


def avatar_png(image_path: str) -> bytes:
    """A photo file, cropped to a centred square and scaled for the account."""
    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtGui import QImage

    img = QImage(image_path)
    if img.isNull():
        raise AccountError("That file isn't an image Mike can read. Try a PNG or JPEG.",
                           code="bad_image")
    side = min(img.width(), img.height())
    img = img.copy((img.width() - side) // 2, (img.height() - side) // 2, side, side)
    img = img.scaled(AVATAR_SIZE, AVATAR_SIZE, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


_manager: AccountManager | None = None


def manager() -> AccountManager:
    global _manager
    if _manager is None:
        _manager = AccountManager()
    return _manager


def reset_for_tests() -> None:
    global _manager
    _manager = None
