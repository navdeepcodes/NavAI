"""Process-level safety: one Mike at a time, and no crash goes unrecorded.

Single instance. Opening Mike while he's already running used to start a
second copy: a second tray icon, a second wake-word listener fighting the
first for the microphone, a second editor bridge failing to bind its port.
Now the new launch finds the running Mike, asks it to come forward, and
exits — the way every desktop app behaves.

Crash capture. An exception nobody caught (in the GUI thread, or any worker
thread) is written to the log with its traceback instead of disappearing into
a console the packaged app doesn't have, and a native crash (an access
violation inside Qt or an audio driver) leaves a Python traceback in
crash.log via faulthandler. "Report a problem" bundles both.
"""
from __future__ import annotations

import faulthandler
import getpass
import re
import sys
import threading

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from hostplatform import storage
from logs.logger import logger

_crash_file = None


def crash_log_path():
    return storage.log_path("crash.log")


def install_crash_handlers() -> None:
    """Record every uncaught exception and native crash. Idempotent."""
    global _crash_file
    if _crash_file is None:
        try:
            _crash_file = open(crash_log_path(), "a", encoding="utf-8")
            faulthandler.enable(file=_crash_file, all_threads=True)
        except Exception:
            logger.debug("faulthandler unavailable.", exc_info=True)

    previous = sys.excepthook

    def _hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            return previous(exc_type, exc, tb)
        logger.critical("Uncaught exception — Mike carried on.", exc_info=(exc_type, exc, tb))
        # PySide keeps the event loop running after a slot raises; keep that
        # behaviour (Mike stays up) rather than exiting on a single bad slot.

    def _thread_hook(args):
        if args.exc_type is SystemExit:
            return
        logger.error("Uncaught exception in thread %s.",
                     getattr(args.thread, "name", "?"),
                     exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    if getattr(sys.excepthook, "_mike", False) is False:
        _hook._mike = True  # type: ignore[attr-defined]
        sys.excepthook = _hook
        threading.excepthook = _thread_hook


def _server_name() -> str:
    try:
        user = getpass.getuser()
    except Exception:
        user = "user"
    return "Mike-" + re.sub(r"[^A-Za-z0-9_.-]", "_", user)


class SingleInstance(QObject):
    """Claim being the one running Mike, or hand over to the one that is."""

    #: Another launch asked this Mike to come forward.
    activated = Signal()

    def __init__(self, name: str | None = None, parent=None) -> None:
        super().__init__(parent)
        self._name = name or _server_name()
        self._server: QLocalServer | None = None

    def claim(self) -> bool:
        """True if this process is now *the* Mike; False if one was already
        running (it has been asked to show itself)."""
        probe = QLocalSocket()
        probe.connectToServer(self._name)
        if probe.waitForConnected(400):
            probe.write(b"show\n")
            probe.flush()
            probe.waitForBytesWritten(400)
            probe.disconnectFromServer()
            return False
        # Nobody answered: any leftover endpoint is from a Mike that crashed.
        QLocalServer.removeServer(self._name)
        self._server = QLocalServer(self)
        self._server.setSocketOptions(QLocalServer.UserAccessOption)
        if not self._server.listen(self._name):
            logger.warning("Single-instance guard could not listen: %s",
                           self._server.errorString())
            return True          # never let the guard stop Mike starting
        self._server.newConnection.connect(self._on_connection)
        return True

    def _on_connection(self) -> None:
        while self._server is not None and self._server.hasPendingConnections():
            sock = self._server.nextPendingConnection()
            sock.readyRead.connect(lambda s=sock: self._on_message(s))
            sock.disconnected.connect(sock.deleteLater)

    def _on_message(self, sock: QLocalSocket) -> None:
        data = bytes(sock.readAll())
        if b"show" in data:
            self.activated.emit()

    def release(self) -> None:
        if self._server is not None:
            self._server.close()
            self._server = None
