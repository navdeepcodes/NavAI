"""One background download of Mike's model, shared by everything that needs it.

A new user used to meet the multi-GB model download at their *first message*:
Mike sat on "Downloading..." for as long as it took (over twenty minutes on a
slow connection), and until then there was nothing useful to do. It now starts
as soon as Mike opens and finds the model missing, so it runs while the person
takes the welcome tour and grants permissions.

Two things need the same download -- the startup check that shows progress in
the banner, and a first message sent before it finishes -- so it lives here
once. Starting it twice must not download twice, and a message sent mid-way
must follow the download that is already running rather than begin another.
Ollama resumes a partly finished pull, so a failed or interrupted download
costs only the part not yet fetched.
"""
from __future__ import annotations

import re
import threading
import time
from collections.abc import Iterator

from logs.logger import logger

_PERCENT = re.compile(r"(\d{1,3})\s*%")
#: How often a waiting caller looks for news.
POLL_SECONDS = 0.4


class ModelDownload:

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self.state = "idle"            # idle | downloading | done | failed
        self.percent: int | None = None
        self.detail = ""
        self.error = None              # a BrainError when state == "failed"

    # ── what is happening ─────────────────────────────────
    def active(self) -> bool:
        return self.state == "downloading"

    def snapshot(self) -> dict:
        return {"state": self.state, "percent": self.percent, "detail": self.detail}

    # ── starting it ───────────────────────────────────────
    def start(self, provider) -> bool:
        """Begin downloading in the background. True if this call started it;
        False if one is already running, or the model has already arrived."""
        if not hasattr(provider, "pull_model"):
            return False
        with self._lock:
            if self.state in ("downloading", "done"):
                return False
            self.state, self.percent, self.detail, self.error = "downloading", None, "", None
            self._thread = threading.Thread(
                target=self._run, args=(provider,), name="model-download", daemon=True)
            self._thread.start()
        logger.info("Model download started in the background.")
        return True

    def _run(self, provider) -> None:
        from brain.providers.base import BrainError

        failure = None
        try:
            for update in provider.pull_model():
                if isinstance(update, BrainError):
                    failure = update
                    continue
                self.detail = str(update)
                match = _PERCENT.search(self.detail)
                if match:
                    self.percent = min(100, int(match.group(1)))
        except Exception as exc:  # a broken provider must not leave "downloading" forever
            logger.exception("Model download crashed.")
            failure = BrainError(kind="model_missing", message=f"The download stopped: {exc}")
        with self._lock:
            if failure is None:
                self.state, self.percent, self.error = "done", 100, None
                logger.info("Model download finished.")
            else:
                self.state, self.error = "failed", failure
                logger.warning("Model download failed: %s", getattr(failure, "message", failure))

    # ── following it (a message sent while it runs) ───────
    def follow(self, provider) -> Iterator[object]:
        """Start the download if nothing has, then yield each new progress
        line until it ends. A BrainError is the last thing yielded on failure.
        Closing this generator (the user pressed Stop) leaves the download
        running; only the waiting stops."""
        self.start(provider)
        last = None
        while True:
            snapshot = self.snapshot()
            line = snapshot["detail"]
            if line and line != last:
                last = line
                yield line
            if snapshot["state"] == "failed":
                yield self.error
                return
            if snapshot["state"] in ("done", "idle"):
                return
            time.sleep(POLL_SECONDS)


#: The one shared download.
download = ModelDownload()
