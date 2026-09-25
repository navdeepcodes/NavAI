"""Signing in with Google (or another provider) from a desktop app.

The standard desktop pattern (RFC 8252): Mike opens the sign-in page in the
person's browser, with a redirect back to a one-shot listener on 127.0.0.1.
Supabase hands back a one-time code there; Mike exchanges it — with the PKCE
verifier only this process knows — for a session. Passwords never pass
through Mike, and an intercepted code is useless without the verifier.

The Supabase project must allow the redirect URL: add
    http://127.0.0.1:*/auth/callback
under Authentication → URL Configuration → Redirect URLs.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

#: Tried in order, so the redirect URL is predictable if a project prefers to
#: list exact ports instead of the wildcard.
PORTS = (53682, 53683, 53684, 0)
PATH = "/auth/callback"


def pkce_pair() -> tuple[str, str]:
    """(verifier, challenge) — S256, as RFC 7636 describes."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


_PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Mike</title>
<style>body{{margin:0;height:100vh;display:flex;align-items:center;justify-content:center;
background:#F6F3EE;font-family:Georgia,'Source Serif 4',serif;color:#1A1714}}
div{{max-width:420px;padding:36px;background:#FBFAF7;border:1px solid #E6E1D8;border-radius:16px}}
h1{{font-size:22px;margin:0 0 10px}}p{{font-size:15px;line-height:1.6;color:#4A443C;margin:0}}</style>
</head><body><div><h1>{title}</h1><p>{body}</p></div></body></html>"""


class Receiver:
    """Waits for one redirect on 127.0.0.1; `.result` holds its query."""

    def __init__(self) -> None:
        self.result: dict[str, str] | None = None
        self._done = threading.Event()
        self._server = self._bind()
        # handle_request() returns every half second, so close() is prompt.
        self._server.timeout = 0.5
        self.port = self._server.server_address[1]
        threading.Thread(target=self._serve, daemon=True).start()

    @property
    def redirect_uri(self) -> str:
        return f"http://127.0.0.1:{self.port}{PATH}"

    def _bind(self) -> HTTPServer:
        receiver = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_a):
                pass

            def do_GET(self):
                url = urlparse(self.path)
                if url.path != PATH:
                    self.send_response(404)
                    self.end_headers()
                    return
                query = {k: v[0] for k, v in parse_qs(url.query).items()}
                ok = "code" in query
                page = _PAGE.format(
                    title="You're signed in." if ok else "That didn't work.",
                    body=("You can close this tab and go back to Mike." if ok else
                          "Go back to Mike and try again. "
                          + (query.get("error_description", "") or "")[:200]))
                body = page.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                receiver.result = query
                receiver._done.set()

        last: OSError | None = None
        for port in PORTS:
            try:
                return HTTPServer(("127.0.0.1", port), Handler)
            except OSError as exc:
                last = exc
        raise last or OSError("no free port")

    def _serve(self) -> None:
        try:
            while not self._done.is_set():
                self._server.handle_request()
        except (OSError, ValueError):
            pass  # closed underneath us — close() was called
        finally:
            try:
                self._server.server_close()
            except Exception:
                pass

    def wait(self, timeout: float) -> dict[str, str] | None:
        self._done.wait(timeout)
        return self.result

    def close(self) -> None:
        self._done.set()
