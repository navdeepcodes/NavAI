"""Is Mike's brain ready? Asked in the background, answered in words.

Mike used to discover that Ollama wasn't running only when you asked your
first question — after a wait, as an error. Now the check runs at startup
(off the GUI thread) and whenever you ask for it, and the answer arrives as a
plain status: ready, starting, not running (with "Start it for me"), or not
installed (with "Get Ollama").
"""
from __future__ import annotations

import threading
import time

from PySide6.QtCore import QObject, Signal


class BrainHealth(QObject):
    """Runs brain checks off the GUI thread and reports the result."""

    #: dict with: state ("ready" | "no_model" | "not_running" | "not_installed"
    #: | "starting" | "checking"), title, detail, can_start (bool)
    changed = Signal(dict)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._busy = False
        self.last: dict = {"state": "checking", "title": "Checking Mike's brain…",
                           "detail": "", "can_start": False}

    def check(self) -> None:
        if self._busy:
            return
        self._busy = True
        self._emit({**self.last, "state": "checking", "title": "Checking Mike's brain…"})
        threading.Thread(target=self._run_check, name="brain-health", daemon=True).start()

    def start_ollama(self) -> None:
        """Start Ollama, then keep checking until it answers (or give up)."""
        if self._busy:
            return
        self._busy = True
        self._emit({"state": "starting", "title": "Starting Ollama…",
                    "detail": "This usually takes a few seconds.", "can_start": False})
        threading.Thread(target=self._run_start, name="brain-start", daemon=True).start()

    # ── worker side ───────────────────────────────────────
    def _emit(self, result: dict) -> None:
        self.last = result
        self.changed.emit(result)

    def _run_check(self) -> None:
        try:
            result = self._probe()
            self._emit(result)
            if result["state"] == "no_model":
                self._download_and_report()
        finally:
            self._busy = False

    def _download_and_report(self) -> None:
        """Mike is open but his model isn't downloaded: start it now, while
        the person takes the tour, and keep the banner honest until it ends.
        (It used to start only at their first message.)"""
        import logging

        from brain import model_download
        try:
            from brain.providers import get_provider
            model_download.download.start(get_provider())
        except Exception:
            logging.getLogger("Mike").exception("Could not start the model download.")
            return
        while model_download.download.active():
            time.sleep(1.5)
            self._emit(self._probe())
        self._emit(self._probe())

    def _run_start(self) -> None:
        try:
            from brain import ollama_launcher
            if not ollama_launcher.start():
                self._emit(self._probe())
                return
            deadline = time.time() + 25
            result = self._probe()
            while result["state"] == "not_running" and time.time() < deadline:
                time.sleep(1.0)
                result = self._probe()
            self._emit(result)
        finally:
            self._busy = False

    @staticmethod
    def _probe() -> dict:
        from brain import model_download, ollama_launcher
        snapshot = model_download.download.snapshot()
        if snapshot["state"] == "downloading":
            percent = snapshot["percent"]
            progress = f"{percent}% done. " if percent is not None else ""
            return {"state": "downloading", "title": "Getting Mike's brain ready",
                    "detail": (f"{progress}This is a one-time download of a few GB, running "
                               "in the background. Mike can answer as soon as it finishes."),
                    "can_start": False}
        try:
            from brain.diagnostics import check_brain
            r = check_brain()
        except Exception as exc:
            r = {"reachable": False, "model_pulled": False, "detail": str(exc), "model": ""}
        model = r.get("model") or "the model"
        if r.get("reachable") and r.get("model_pulled"):
            return {"state": "ready", "title": "Ready",
                    "detail": f"{model} is running on this computer.", "can_start": False}
        if r.get("reachable"):
            return {"state": "no_model", "title": "Almost ready",
                    "detail": (f"Mike's brain ({model}) hasn't finished downloading — "
                               "a few GB, once. Ask him something and he'll carry on."),
                    "can_start": False}
        if ollama_launcher.installed():
            return {"state": "not_running", "title": "Mike's brain isn't running",
                    "detail": ("Ollama, which runs Mike's brain on this computer, is "
                               "installed but not started."),
                    "can_start": True}
        return {"state": "not_installed", "title": "Mike needs Ollama to think",
                "detail": ("Ollama runs Mike's brain privately on this computer. "
                           "Install it (free), then come back."),
                "can_start": False}
