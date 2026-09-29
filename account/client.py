"""Supabase Auth, REST and Storage — the handful of calls Mike's accounts use.

Plain HTTP over `requests`, following the same public API supabase-js uses,
so there is no SDK to bundle and nothing here that isn't exercised by the
end-to-end tests against a real Supabase (tests/test_account_e2e.py).

Every failure is an AccountError carrying a sentence a person can act on;
the raw server message is kept for the log. Tokens are never logged.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

import requests

from logs.logger import logger

TIMEOUT = 15


class AccountError(Exception):
    """Something the person should hear about, in words they can act on."""

    def __init__(self, message: str, code: str = "", status: int = 0,
                 detail: str = "", retry_after: int = 0) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status
        self.detail = detail
        self.retry_after = retry_after

    @property
    def session_ended(self) -> bool:
        """The saved sign-in is no longer valid: sign in again."""
        return self.code in _SESSION_ENDED


class NetworkError(AccountError):
    """The account service couldn't be reached — nothing is wrong with the account."""


_SESSION_ENDED = {
    "session_not_found", "session_expired", "refresh_token_not_found",
    "refresh_token_already_used", "bad_jwt", "user_not_found", "no_authorization",
}

_FRIENDLY = {
    "invalid_credentials": "That email and password don't match. Check them, or reset your password.",
    "email_not_confirmed": "Confirm your email first — enter the code we sent you.",
    "user_already_exists": "There's already an account with that email. Sign in instead.",
    "email_exists": "There's already an account with that email.",
    "otp_expired": "That code isn't right or has expired. Check it, or ask for a new one.",
    "otp_disabled": "There's no account with that email yet. Create one instead.",
    "same_password": "Choose a password you haven't used for this account before.",
    "email_address_invalid": "Enter a valid email address.",
    "validation_failed": "Check what you entered and try again.",
    "signup_disabled": "New accounts aren't open right now.",
    "email_provider_disabled": "Signing in with email isn't turned on for Mike's accounts.",
    "provider_disabled": "That way of signing in isn't turned on for Mike's accounts.",
    "over_request_rate_limit": "Too many attempts. Wait a minute, then try again.",
    "over_email_send_rate_limit": "Wait a moment before asking for another email.",
    "email_address_not_authorized": (
        "Mike's account service can't send email to that address yet. "
        "(The Supabase project needs its own email sender — see docs/ACCOUNTS.md.)"),
    "reauthentication_needed": "Confirm it's you — enter the code we just emailed you.",
    "reauthentication_not_valid": "That code isn't right or has expired. Ask for a new one.",
    "user_banned": "This account has been suspended.",
    "session_not_found": "You've been signed out. Sign in again.",
    "session_expired": "You've been signed out. Sign in again.",
    "refresh_token_not_found": "You've been signed out. Sign in again.",
    "refresh_token_already_used": "You've been signed out. Sign in again.",
    "bad_jwt": "You've been signed out. Sign in again.",
    "user_not_found": "This account no longer exists.",
    "flow_state_expired": "That sign-in took too long. Try again.",
    "flow_state_not_found": "That sign-in link has already been used. Try again.",
    "bad_code_verifier": "That sign-in couldn't be completed. Try again.",
}

_OFFLINE = "Can't reach Mike's account service. Check your internet connection and try again."


@dataclass
class Session:
    access_token: str
    refresh_token: str
    expires_at: float
    user: dict = field(default_factory=dict)

    @classmethod
    def from_response(cls, data: dict) -> "Session":
        expires_at = data.get("expires_at")
        if not expires_at:
            expires_at = time.time() + float(data.get("expires_in") or 3600)
        return cls(access_token=data["access_token"], refresh_token=data["refresh_token"],
                   expires_at=float(expires_at), user=data.get("user") or {})

    @property
    def user_id(self) -> str:
        return str(self.user.get("id") or "")

    def expires_in(self) -> float:
        return self.expires_at - time.time()

    def to_dict(self) -> dict:
        return {"access_token": self.access_token, "refresh_token": self.refresh_token,
                "expires_at": self.expires_at, "user": self.user}

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        return cls(access_token=data["access_token"], refresh_token=data["refresh_token"],
                   expires_at=float(data["expires_at"]), user=data.get("user") or {})


def _error_from(resp: requests.Response) -> AccountError:
    try:
        body = resp.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    code = str(body.get("error_code") or body.get("error") or "")
    if not code and isinstance(body.get("code"), str):
        code = body["code"]
    detail = str(body.get("msg") or body.get("message") or body.get("error_description")
                 or resp.text[:300] or "")
    # PostgREST / Storage shapes
    if not code and resp.status_code in (401, 403) and "jwt" in detail.lower():
        code = "bad_jwt"
    if code == "invalid_grant" and "refresh token" in detail.lower():
        code = "refresh_token_not_found"
    if code == "invalid_grant" and "invalid login" in detail.lower():
        code = "invalid_credentials"
    if code == "invalid_grant" and "email not confirmed" in detail.lower():
        code = "email_not_confirmed"
    retry_after = 0
    seconds = re.search(r"after (\d+) seconds?", detail)
    if seconds:
        retry_after = int(seconds.group(1))
    if code == "weak_password":
        reasons = (body.get("weak_password") or {}).get("reasons") or []
        if "pwned" in reasons:
            message = "That password has appeared in a data breach. Choose a different one."
        else:
            message = "Choose a stronger password — at least 8 characters."
    elif code == "over_email_send_rate_limit" and retry_after:
        message = f"Wait {retry_after} seconds before asking for another email."
    else:
        message = _FRIENDLY.get(code) or (
            "Something went wrong with Mike's account service. Try again in a moment."
            if resp.status_code >= 500 else
            (detail if detail and len(detail) < 160 else "That didn't work. Try again."))
    return AccountError(message, code=code, status=resp.status_code, detail=detail,
                        retry_after=retry_after)


class SupabaseClient:
    """One Supabase project. Stateless: sessions are passed in, not held."""

    def __init__(self, url: str, key: str, timeout: float = TIMEOUT) -> None:
        self.url = url.rstrip("/")
        self.key = key
        self.timeout = timeout
        self._http = requests.Session()

    # ── plumbing ─────────────────────────────────────────────────────────
    def _headers(self, access: str | None = None, extra: dict | None = None) -> dict:
        from config import settings
        h = {"apikey": self.key, "X-Client-Info": f"mike/{settings.VERSION}"}
        if access:
            h["Authorization"] = f"Bearer {access}"
        if extra:
            h.update(extra)
        return h

    def _request(self, method: str, path: str, *, access: str | None = None,
                 json: Any = None, data: bytes | None = None, params: dict | None = None,
                 headers: dict | None = None, ok=(200, 201, 204)) -> requests.Response:
        try:
            resp = self._http.request(method, self.url + path, params=params, json=json,
                                      data=data, headers=self._headers(access, headers),
                                      timeout=self.timeout)
        except (requests.ConnectionError, requests.Timeout) as exc:
            logger.info("Account service unreachable (%s %s): %s", method, path,
                        type(exc).__name__)
            raise NetworkError(_OFFLINE, code="network") from None
        if resp.status_code not in ok:
            err = _error_from(resp)
            logger.info("Account call %s %s failed: %s %s (%s)", method, path.split("?")[0],
                        resp.status_code, err.code or "-", err.detail[:160])
            raise err
        return resp

    @staticmethod
    def _json(resp: requests.Response) -> Any:
        if resp.status_code == 204 or not resp.content:
            return {}
        try:
            return resp.json()
        except ValueError:
            return {}

    # ── auth ─────────────────────────────────────────────────────────────
    def sign_up(self, email: str, password: str, name: str = "") -> tuple[Session | None, dict]:
        """Creates the account. Returns (session, user): a session if the project
        signs people in straight away, otherwise None — a code was emailed."""
        body = {"email": email, "password": password,
                "data": {"display_name": name} if name else {}}
        data = self._json(self._request("POST", "/auth/v1/signup", json=body))
        if data.get("access_token"):
            s = Session.from_response(data)
            return s, s.user
        user = data.get("user") or data
        # With email confirmation on, Supabase answers a sign-up for an address
        # that already has an account with a stand-in user that has no
        # identities, rather than say so (to not reveal who has an account).
        if isinstance(user.get("identities"), list) and not user["identities"]:
            raise AccountError(_FRIENDLY["user_already_exists"], code="user_already_exists")
        return None, user

    def sign_in(self, email: str, password: str) -> Session:
        data = self._json(self._request("POST", "/auth/v1/token",
                                        params={"grant_type": "password"},
                                        json={"email": email, "password": password}))
        return Session.from_response(data)

    def send_code(self, email: str, create_user: bool = False) -> None:
        """Emails a one-time sign-in code."""
        self._request("POST", "/auth/v1/otp", json={"email": email, "create_user": create_user})

    def resend(self, kind: str, email: str) -> None:
        """kind: "signup" or "email_change"."""
        self._request("POST", "/auth/v1/resend", json={"type": kind, "email": email})

    def send_recovery(self, email: str) -> None:
        self._request("POST", "/auth/v1/recover", json={"email": email})

    def verify(self, email: str, code: str, kind: str) -> Session | None:
        """kind: "email" (sign-up or sign-in code), "recovery" or "email_change".
        Returns the session it starts — or None when an email change still
        needs the code sent to the other address."""
        data = self._json(self._request("POST", "/auth/v1/verify",
                                        json={"type": kind, "email": email,
                                              "token": code.strip().replace(" ", "")}))
        return Session.from_response(data) if data.get("access_token") else None

    def refresh(self, refresh_token: str) -> Session:
        data = self._json(self._request("POST", "/auth/v1/token",
                                        params={"grant_type": "refresh_token"},
                                        json={"refresh_token": refresh_token}))
        return Session.from_response(data)

    def get_user(self, access: str) -> dict:
        return self._json(self._request("GET", "/auth/v1/user", access=access))

    def update_user(self, access: str, **fields) -> dict:
        body = {k: v for k, v in fields.items() if v is not None}
        return self._json(self._request("PUT", "/auth/v1/user", access=access, json=body))

    def reauthenticate(self, access: str) -> None:
        """Emails a code that confirms it's really you (for a password change)."""
        self._request("GET", "/auth/v1/reauthenticate", access=access)

    def sign_out(self, access: str) -> None:
        self._request("POST", "/auth/v1/logout", access=access, params={"scope": "local"})

    def authorize_url(self, provider: str, redirect_to: str, code_challenge: str) -> str:
        query = urlencode({"provider": provider, "redirect_to": redirect_to,
                           "code_challenge": code_challenge,
                           "code_challenge_method": "s256"})
        return f"{self.url}/auth/v1/authorize?{query}"

    def exchange_code(self, auth_code: str, code_verifier: str) -> Session:
        data = self._json(self._request("POST", "/auth/v1/token",
                                        params={"grant_type": "pkce"},
                                        json={"auth_code": auth_code,
                                              "code_verifier": code_verifier}))
        return Session.from_response(data)

    # ── profile ──────────────────────────────────────────────────────────
    def get_profile(self, access: str, user_id: str) -> dict | None:
        rows = self._json(self._request(
            "GET", "/rest/v1/profiles", access=access,
            params={"id": f"eq.{user_id}", "select": "display_name,avatar_path,updated_at"}))
        return rows[0] if isinstance(rows, list) and rows else None

    def save_profile(self, access: str, user_id: str, **fields) -> dict:
        body = {"id": user_id, **fields}
        rows = self._json(self._request(
            "POST", "/rest/v1/profiles", access=access, json=body,
            params={"on_conflict": "id"},
            headers={"Prefer": "resolution=merge-duplicates,return=representation"}))
        return rows[0] if isinstance(rows, list) and rows else body

    # ── avatar ───────────────────────────────────────────────────────────
    def upload_avatar(self, access: str, path: str, data: bytes,
                      content_type: str = "image/png") -> None:
        self._request("POST", f"/storage/v1/object/avatars/{path}", access=access, data=data,
                      headers={"Content-Type": content_type, "x-upsert": "true",
                               "cache-control": "3600"})

    def download_avatar(self, access: str, path: str) -> bytes:
        return self._request("GET", f"/storage/v1/object/authenticated/avatars/{path}",
                             access=access).content

    def remove_avatar(self, access: str, path: str) -> None:
        self._request("DELETE", f"/storage/v1/object/avatars/{path}", access=access,
                      ok=(200, 204, 404))

    # ── deletion ─────────────────────────────────────────────────────────
    def delete_account(self, access: str) -> None:
        self._request("POST", "/rest/v1/rpc/delete_account", access=access, json={})
