"""Local HTTP bridge between Mike and an editor extension.

Plain stdlib HTTP on 127.0.0.1 — no dependencies on either side, and the
VS Code extension can talk to it with Node's built-in http module. Nothing
leaves the machine.

Shape:
    POST /context   extension pushes a context snapshot when it changes
    GET  /commands  extension long-polls; returns a queued command or 204
    POST /result    extension returns the outcome of a command
    GET  /health    liveness probe
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from logs.logger import logger

HOST = "127.0.0.1"
PORT = 8787

# How long a command poll is held open before returning empty. Long enough to
# avoid busy polling, short enough that the extension notices a dead server.
POLL_HOLD_SECONDS = 20.0

# An editor that hasn't checked in for this long is treated as gone.
CONNECTION_TIMEOUT = 45.0


class IDEBridge:

    def __init__(self, host: str = HOST, port: int = PORT) -> None:
        self._host = host
        self._port = port

        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

        self._lock = threading.Lock()

        # Several editor windows can be open at once. Each is tracked
        # separately so they don't overwrite each other, and the focused one
        # is what Mike reads and acts on.
        self._windows: dict[str, dict] = {}
        self._last_seen: float = 0.0

        self._pending: list[dict] = []
        self._results: dict[str, dict] = {}
        self._command_ready = threading.Condition(self._lock)
        self._result_ready = threading.Condition(self._lock)

    # ── Lifecycle ────────────────────────────────────────────

    def start(self) -> bool:
        if self._server is not None:
            return True

        bridge = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args) -> None:
                pass  # stdlib logs every request to stderr otherwise

            def _send(self, code: int, payload: dict | None = None) -> None:
                body = json.dumps(payload or {}).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if body:
                    self.wfile.write(body)

            def _read_json(self) -> dict:
                length = int(self.headers.get("Content-Length") or 0)
                if not length:
                    return {}
                try:
                    return json.loads(self.rfile.read(length).decode())
                except Exception:
                    return {}

            def do_GET(self):
                if self.path.startswith("/commands"):
                    window_id = ""
                    if "?" in self.path:
                        from urllib.parse import parse_qs, urlparse

                        query = parse_qs(urlparse(self.path).query)
                        window_id = (query.get("windowId") or [""])[0]

                    command = bridge._await_command(window_id)
                    if command is None:
                        self._send(204)
                    else:
                        self._send(200, command)
                    return

                if self.path.startswith("/health"):
                    self._send(200, {"ok": True, "connected": bridge.is_connected()})
                    return

                self._send(404, {"error": "unknown endpoint"})

            def do_POST(self):
                if self.path.startswith("/context"):
                    bridge._store_context(self._read_json())
                    self._send(200, {"ok": True})
                    return

                if self.path.startswith("/result"):
                    bridge._store_result(self._read_json())
                    self._send(200, {"ok": True})
                    return

                self._send(404, {"error": "unknown endpoint"})

        try:
            self._server = ThreadingHTTPServer((self._host, self._port), Handler)
        except OSError as exc:
            logger.warning("IDE bridge could not bind %s:%s — %s", self._host, self._port, exc)
            self._server = None
            return False

        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

        logger.info("IDE bridge listening on %s:%s", self._host, self._port)
        return True

    def stop(self) -> None:
        if self._server is None:
            return

        # Release anything parked on a long poll so the server can shut down.
        with self._lock:
            self._command_ready.notify_all()
            self._result_ready.notify_all()

        self._server.shutdown()
        self._server.server_close()
        self._server = None
        logger.info("IDE bridge stopped.")

    # ── Connection state ─────────────────────────────────────

    def is_connected(self) -> bool:
        with self._lock:
            return (
                self._last_seen > 0.0
                and (time.time() - self._last_seen) < CONNECTION_TIMEOUT
            )

    def raw_context(self) -> dict:
        with self._lock:
            window = self.__preferred_window_unlocked()
            return dict(window["payload"]) if window else {}

    def __connected_unlocked(self) -> bool:
        return (
            self._last_seen > 0.0
            and (time.time() - self._last_seen) < CONNECTION_TIMEOUT
        )

    def __live_windows_unlocked(self) -> list[dict]:
        cutoff = time.time() - CONNECTION_TIMEOUT
        return [w for w in self._windows.values() if w["seen"] >= cutoff]

    def __preferred_window_unlocked(self) -> dict | None:
        """
        The window the user is actually looking at, falling back to whichever
        checked in most recently.
        """

        live = self.__live_windows_unlocked()
        if not live:
            return None

        focused = [w for w in live if w.get("focused")]
        pool = focused or live

        return max(pool, key=lambda w: w["seen"])

    def preferred_window_id(self) -> str:
        with self._lock:
            window = self.__preferred_window_unlocked()
            return window["id"] if window else ""

    # ── Context ingest ───────────────────────────────────────

    def _store_context(self, payload: dict) -> None:
        payload = payload or {}
        window_id = str(payload.get("windowId") or "default")

        with self._lock:
            self._windows[window_id] = {
                "id": window_id,
                "payload": payload,
                "focused": bool(payload.get("focused")),
                "seen": time.time(),
            }
            self._last_seen = time.time()

            # Drop windows that have been gone a while so a long session
            # doesn't accumulate dead entries.
            cutoff = time.time() - (CONNECTION_TIMEOUT * 4)
            for key in [k for k, w in self._windows.items() if w["seen"] < cutoff]:
                self._windows.pop(key, None)

    # ── Commands out to the editor ───────────────────────────

    def send_command(self, action: str, params: dict, timeout: float = 12.0) -> dict:
        """Queue a command and block until the editor reports back."""

        if not self.is_connected():
            return {"ok": False, "error": "No editor is connected."}

        command_id = uuid.uuid4().hex
        command = {"id": command_id, "action": action, "params": params}

        with self._lock:
            self._pending.append(command)
            self._command_ready.notify_all()

        deadline = time.time() + timeout
        with self._lock:
            while command_id not in self._results:
                remaining = deadline - time.time()
                if remaining <= 0:
                    self._results.pop(command_id, None)
                    return {"ok": False, "error": "The editor didn't respond in time."}
                self._result_ready.wait(remaining)

            return self._results.pop(command_id)

    def _await_command(self, window_id: str = "") -> dict | None:
        """
        Held open by the extension's long poll until work shows up. Commands
        are only handed to the window the user is actually in, so an edit
        can't land in a different project's window.
        """

        deadline = time.time() + POLL_HOLD_SECONDS

        with self._lock:
            # A poll is itself proof that window is alive.
            self._last_seen = time.time()
            if window_id and window_id in self._windows:
                self._windows[window_id]["seen"] = time.time()

            while True:
                if self._pending:
                    preferred = self.__preferred_window_unlocked()
                    target = preferred["id"] if preferred else ""

                    if not window_id or not target or window_id == target:
                        return self._pending.pop(0)

                remaining = deadline - time.time()
                if remaining <= 0:
                    return None
                self._command_ready.wait(remaining)

    def _store_result(self, payload: dict) -> None:
        command_id = payload.get("id")
        if not command_id:
            return

        with self._lock:
            self._results[command_id] = payload.get("result") or {"ok": True}
            self._last_seen = time.time()
            self._result_ready.notify_all()
