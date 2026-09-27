"""Connecting a student's own Cloudflare account, for Fast mode.

Every Cloudflare account gets a free daily Workers AI allowance. Fast mode runs
Mike's model there -- seconds per turn instead of tens -- on the student's own
account, so the allowance is theirs and nobody is billed.

Connecting is Cloudflare's own OAuth, the same desktop pattern as Google
sign-in (account/loopback.py): Mike opens Cloudflare's page in the browser,
the student signs in or signs up and clicks Allow, and Cloudflare hands a
one-time code back to 127.0.0.1. Mike exchanges it with the PKCE verifier only
this process knows, then finds the account ID itself -- the student never
copies an ID or a token.

The tokens act for the student's account, so they're kept like the Mike
session: DPAPI on Windows (readable only by this Windows user on this
computer), owner-only elsewhere. They can do Workers AI and read account
settings -- the scopes the client was registered with -- and nothing else.
"""
from __future__ import annotations

import json
import secrets
import threading
import time
import webbrowser
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode

import requests

from account import session_store
from account.loopback import Receiver, pkce_pair
from logs.logger import logger

AUTH_URL = "https://dash.cloudflare.com/oauth2/auth"
TOKEN_URL = "https://dash.cloudflare.com/oauth2/token"
REVOKE_URL = "https://dash.cloudflare.com/oauth2/revoke"
API = "https://api.cloudflare.com/client/v4"

#: The redirects registered on the OAuth client, exactly.
CALLBACK_PATH = "/cloudflare/callback"
CALLBACK_PORTS = (53682, 53683, 53684)

#: Renew the access token this long before it expires, in the background, so
#: no question waits for it. Renewing doesn't withdraw the old token --
#: measured, it was still accepted 23s later -- so it carries on meanwhile.
RENEW_AHEAD = 300
#: Closer than this to expiring, a token is renewed before it's used.
RENEW_BY = 60
#: A token issued moments ago can be refused -- measured, one was refused
#: 0.4s after it was issued and accepted a second later. For this long after
#: it's issued, a refusal means "not yet", and gets another go after SETTLE.
FRESH = 10
SETTLE = 1.5

_lock = threading.Lock()            # renewing: one at a time, each from the latest file
_renewing = threading.Event()       # a background renewal is under way
_lost = threading.Event()           # Cloudflare refused to renew: said once, then cleared
_cache: tuple[tuple, dict] | None = None


class CloudflareError(RuntimeError):
    """Something a person can read; the detail goes to the log."""


def _settings():
    from config import settings
    return settings


def _file() -> Path:
    return session_store.folder() / "cloudflare.bin"


def _stamp(path: Path) -> tuple:
    """What changes whenever the file is saved again. Each save puts a new
    file in place (session_store._write_private), so its file ID changes even
    when two saves land in the same tick of the clock."""
    st = path.stat()
    return st.st_mtime_ns, st.st_ino, st.st_size


def _save(data: dict) -> None:
    global _cache
    path = _file()
    blob = session_store._encode(json.dumps(data).encode("utf-8"))
    for attempt in range(5):
        try:
            session_store._write_private(path, blob)
            break
        except PermissionError:
            # Windows won't replace a file someone has open this instant --
            # a rotated refresh token must not be lost to that: the old one
            # is already spent.
            if attempt == 4:
                raise
            time.sleep(0.05)
    try:
        _cache = (_stamp(path), dict(data))
    except OSError:
        _cache = None


def connection() -> dict | None:
    """The saved connection: account_id, account_name, tokens. None if not
    connected, or if what's saved can't be made sense of (then it's forgotten).

    Asked on every turn (is Fast mode on?), so it's read again only when the
    file has changed. A read that meets the file mid-replace -- Windows
    refuses to open it for that instant -- is tried again, not taken for a
    broken connection: forgetting it then would lose a working one."""
    global _cache
    path = _file()
    try:
        stamp = _stamp(path)
    except FileNotFoundError:
        _cache = None
        return None
    except OSError:
        return dict(_cache[1]) if _cache else None
    if _cache is not None and _cache[0] == stamp:
        return dict(_cache[1])
    blob = None
    for _ in range(5):
        try:
            blob = path.read_bytes()
            break
        except FileNotFoundError:
            return None
        except OSError:
            time.sleep(0.05)
    if blob is None:
        return dict(_cache[1]) if _cache else None
    try:
        data = json.loads(session_store._decode(blob).decode("utf-8"))
    except Exception:
        logger.warning("The saved Cloudflare connection couldn't be read; forgetting it.",
                       exc_info=True)
        path.unlink(missing_ok=True)
        _cache = None
        return None
    if not (data.get("refresh_token") and data.get("account_id")):
        return None
    _cache = (stamp, data)
    return dict(data)


def connected() -> bool:
    return connection() is not None


# ── tokens ───────────────────────────────────────────────────────────────

def _token_request(fields: dict) -> dict:
    fields = {"client_id": _settings().CLOUDFLARE_CLIENT_ID, **fields}
    try:
        response = requests.post(TOKEN_URL, data=fields, timeout=30)
    except requests.RequestException as exc:
        raise CloudflareError("Couldn't reach Cloudflare. Check your internet connection.") from exc
    if response.status_code != 200:
        logger.warning("Cloudflare token request failed: %s %s",
                       response.status_code, response.text[:300])
        raise CloudflareError("Cloudflare didn't accept the connection. Try connecting again.")
    return response.json()


def _with_expiry(tokens: dict, previous: dict | None = None) -> dict:
    out = dict(previous or {})
    out["access_token"] = tokens["access_token"]
    # Refresh tokens rotate: keep the new one when Cloudflare sends one.
    out["refresh_token"] = tokens.get("refresh_token") or out.get("refresh_token")
    out["issued_at"] = time.time()
    out["expires_at"] = out["issued_at"] + float(tokens.get("expires_in") or 3600)
    return out


def access_token() -> str | None:
    """A current access token. None when not connected, or when Cloudflare no
    longer accepts the connection (the student revoked it): then it's
    forgotten, and Settings offers to connect again.

    A token with time left is handed out without waiting on anything; in its
    last minutes it's renewed in the background. Only an expired one -- Mike
    was closed for a while -- is renewed before it's used."""
    data = connection()
    if data is None:
        return None
    left = data.get("expires_at", 0) - time.time()
    if left > RENEW_BY:
        if left < RENEW_AHEAD:
            _renew_in_background()
        return data["access_token"]
    with _lock:
        data = connection()           # again: it may have been renewed while this waited
        if data is None:
            return None
        if data.get("expires_at", 0) - time.time() > RENEW_BY:
            return data["access_token"]
        return _renew(data)


def _renew(data: dict) -> str | None:
    """Under _lock: a new access token for `data`, saved. None when Cloudflare
    can't be reached (the connection is kept) or refuses (it's forgotten)."""
    try:
        fresh = _with_expiry(_token_request({
            "grant_type": "refresh_token", "refresh_token": data["refresh_token"]}), data)
    except CloudflareError:
        latest = connection()
        if latest is not None and latest.get("refresh_token") != data.get("refresh_token"):
            return latest["access_token"]      # renewed meanwhile, by another Mike
        # Offline is not a revocation: keep the connection, use the local
        # model this turn, and try again next time.
        try:
            requests.head(TOKEN_URL, timeout=10)
        except requests.RequestException:
            return None
        logger.warning("Cloudflare no longer accepts Mike's connection; forgetting it.")
        _file().unlink(missing_ok=True)
        _lost.set()
        return None
    _save(fresh)
    return fresh["access_token"]


def _renew_in_background() -> None:
    if _renewing.is_set():
        return
    _renewing.set()

    def run() -> None:
        try:
            with _lock:
                data = connection()
                if data is not None and data.get("expires_at", 0) - time.time() < RENEW_AHEAD:
                    _renew(data)
        except Exception:
            logger.debug("Renewing the Cloudflare token in the background failed.", exc_info=True)
        finally:
            _renewing.clear()

    threading.Thread(target=run, name="cloudflare-renew", daemon=True).start()


def retry_token() -> str | None:
    """Cloudflare just refused the access token (HTTP 401 or 403): the token
    to try once more with, or None when there's nothing left to try.

    A token issued moments ago isn't known everywhere yet: it gets a moment,
    and another go. An older one has been withdrawn: it's renewed -- and if
    Cloudflare won't renew it either, the connection is forgotten."""
    data = connection()
    if data is None:
        return None
    if time.time() - float(data.get("issued_at") or 0) < FRESH:
        time.sleep(SETTLE)
        return data["access_token"]
    with _lock:
        data = connection()
        if data is None:
            return None
        if time.time() - float(data.get("issued_at") or 0) < FRESH:
            token = data["access_token"]       # renewed while this waited
        else:
            token = _renew(data)
    if token:
        time.sleep(SETTLE)                     # brand new: let it be known
    return token


def take_lost() -> bool:
    """Whether Cloudflare stopped accepting the connection since this was last
    asked -- so it can be said once, rather than Mike just getting slower."""
    if _lost.is_set():
        _lost.clear()
        return True
    return False


def account_id() -> str | None:
    data = connection()
    return data.get("account_id") if data else None


# ── connecting ───────────────────────────────────────────────────────────

def authorize_url(redirect_uri: str, challenge: str, state: str) -> str:
    s = _settings()
    return AUTH_URL + "?" + urlencode({
        "response_type": "code",
        "client_id": s.CLOUDFLARE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "scope": " ".join(s.CLOUDFLARE_SCOPES),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })


def _accounts(token: str) -> list[dict]:
    response = requests.get(f"{API}/accounts", headers={"Authorization": f"Bearer {token}"},
                            params={"per_page": 50}, timeout=30)
    if response.status_code != 200:
        logger.warning("Listing Cloudflare accounts failed: %s %s",
                       response.status_code, response.text[:300])
        raise CloudflareError("Connected, but Mike couldn't see your Cloudflare account. "
                              "Try connecting again.")
    return response.json().get("result") or []


def connect(open_browser: Callable[[str], object] = webbrowser.open,
            timeout: float = 300, cancel: threading.Event | None = None) -> dict:
    """Blocking: opens Cloudflare in the browser and waits for Allow. Returns
    {"account_id", "account_name"}; raises CloudflareError with a sentence a
    person can read. Run it off the UI thread."""
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(16)
    try:
        receiver = Receiver(path=CALLBACK_PATH, ports=CALLBACK_PORTS,
                            success="Fast mode is on.")
    except OSError as exc:
        raise CloudflareError("Something on this computer is using the ports Mike needs to "
                              "connect. Close other sign-in windows and try again.") from exc
    try:
        open_browser(authorize_url(receiver.redirect_uri, challenge, state))
        deadline = time.monotonic() + timeout
        result = None
        while result is None and time.monotonic() < deadline:
            if cancel is not None and cancel.is_set():
                raise CloudflareError("Connecting was cancelled.")
            result = receiver.wait(0.5)
    finally:
        receiver.close()
    if not result:
        raise CloudflareError("Cloudflare didn't answer in time. Try connecting again.")
    if result.get("state") != state:
        raise CloudflareError("That answer wasn't for this request. Try connecting again.")
    if "code" not in result:
        detail = result.get("error_description") or result.get("error") or ""
        logger.info("Cloudflare connection declined: %s", detail[:200])
        raise CloudflareError("Cloudflare didn't connect" + (f": {detail[:160]}" if detail else "."))
    tokens = _token_request({"grant_type": "authorization_code", "code": result["code"],
                             "redirect_uri": receiver.redirect_uri, "code_verifier": verifier})
    data = _with_expiry(tokens)
    accounts = _accounts(data["access_token"])
    if not accounts:
        raise CloudflareError("Connected, but no Cloudflare account came with it. "
                              "Try again and pick your account on Cloudflare's page.")
    data["account_id"] = accounts[0]["id"]
    data["account_name"] = accounts[0].get("name") or ""
    with _lock:
        _save(data)
    _lost.clear()
    logger.info("Cloudflare connected (%d account(s) granted).", len(accounts))
    return {"account_id": data["account_id"], "account_name": data["account_name"]}


def disconnect(background: bool = False) -> None:
    """Forget the connection here, and ask Cloudflare to revoke it -- on its
    own thread with `background` (Reset Mike doesn't wait on the network).
    Either way the connection is gone here when this returns."""
    with _lock:
        data = connection()
        _file().unlink(missing_ok=True)
    if not data:
        return
    if background:
        threading.Thread(target=_revoke, args=(data,), name="cloudflare-revoke", daemon=True).start()
    else:
        _revoke(data)


def _revoke(data: dict) -> None:
    try:
        requests.post(REVOKE_URL, data={"token": data["refresh_token"],
                                        "token_type_hint": "refresh_token",
                                        "client_id": _settings().CLOUDFLARE_CLIENT_ID},
                      timeout=15)
    except requests.RequestException:
        logger.info("Couldn't reach Cloudflare to revoke; the connection is forgotten here.")
