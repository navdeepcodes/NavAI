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

_lock = threading.Lock()


class CloudflareError(RuntimeError):
    """Something a person can read; the detail goes to the log."""


def _settings():
    from config import settings
    return settings


def _file() -> Path:
    return session_store.folder() / "cloudflare.bin"


def _save(data: dict) -> None:
    session_store._write_private(_file(), session_store._encode(json.dumps(data).encode("utf-8")))


def connection() -> dict | None:
    """The saved connection: account_id, account_name, tokens. None if not
    connected, or if the file can't be read (then it's forgotten)."""
    path = _file()
    if not path.exists():
        return None
    try:
        data = json.loads(session_store._decode(path.read_bytes()).decode("utf-8"))
        return data if data.get("refresh_token") and data.get("account_id") else None
    except Exception:
        logger.warning("The saved Cloudflare connection couldn't be read; forgetting it.",
                       exc_info=True)
        path.unlink(missing_ok=True)
        return None


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
    out["expires_at"] = time.time() + float(tokens.get("expires_in") or 3600)
    return out


def access_token() -> str | None:
    """A current access token, renewed when it's about to expire. None when
    not connected, or when Cloudflare no longer accepts the connection (the
    student revoked it): then it's forgotten, and Settings offers to connect
    again."""
    with _lock:
        data = connection()
        if data is None:
            return None
        if data.get("expires_at", 0) - time.time() > 60:
            return data["access_token"]
        try:
            data = _with_expiry(_token_request({
                "grant_type": "refresh_token", "refresh_token": data["refresh_token"]}), data)
        except CloudflareError:
            # Offline is not a revocation: keep the connection, use the local
            # model this turn, and try again next time.
            try:
                requests.head(TOKEN_URL, timeout=10)
            except requests.RequestException:
                return None
            logger.warning("Cloudflare no longer accepts Mike's connection; forgetting it.")
            _file().unlink(missing_ok=True)
            return None
        _save(data)
        return data["access_token"]


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
    logger.info("Cloudflare connected (%d account(s) granted).", len(accounts))
    return {"account_id": data["account_id"], "account_name": data["account_name"]}


def disconnect() -> None:
    """Forget the connection here, and ask Cloudflare to revoke it."""
    with _lock:
        data = connection()
        _file().unlink(missing_ok=True)
    if not data:
        return
    try:
        requests.post(REVOKE_URL, data={"token": data["refresh_token"],
                                        "token_type_hint": "refresh_token",
                                        "client_id": _settings().CLOUDFLARE_CLIENT_ID},
                      timeout=15)
    except requests.RequestException:
        logger.info("Couldn't reach Cloudflare to revoke; the connection is forgotten here.")
