"""Keeping Mike current, from inside the app (installer/updates.py does the work).

A quiet check shortly after Mike starts and then twice a day; when a newer
version is out, the chat shows a banner and the choice is the student's:
"Update now" downloads it (checked against the published SHA-256), Mike quits,
the new version swaps itself in and starts. Nothing updates on its own, and a
half-finished update never leaves Mike broken (installer/core.copy_tree keeps
the old version if the swap fails).

Only an installed Mike checks automatically: a copy run from source or from a
folder in Downloads has nothing sensible to replace. Settings → General turns
the automatic check off; Settings → About can always check by hand.
"""
from __future__ import annotations

import sys
import threading

from PySide6.QtCore import QObject, QTimer, Signal

from logs.logger import logger

FIRST_CHECK_MS = 25_000
EVERY_MS = 12 * 60 * 60 * 1000


def installed_build() -> bool:
    """A packaged Mike running from its install location -- the only kind an
    update can replace."""
    if not getattr(sys, "frozen", False):
        return False
    try:
        from installer import core
        return core.running_from_install_dir()
    except Exception:
        return False


class Updater(QObject):

    #: A newer version is out (installer.updates.Update)
    available = Signal(object)
    #: Downloading: (percent, what's happening)
    progress = Signal(int, str)
    #: The update couldn't be fetched or started, in words for the student
    failed = Signal(str)
    #: The result of a check, for Settings → About ("Mike is up to date")
    status = Signal(str)
    #: Mike was just updated to this version (said once, after the restart)
    updated = Signal(str)
    #: The new version is unpacked and waiting for this Mike to quit
    ready = Signal()

    def __init__(self, quit_app=None, parent=None) -> None:
        super().__init__(parent)
        self._quit_app = quit_app
        self._offer = None
        self._busy = False
        self.last_status = ""
        self.status.connect(self._remember)
        self.ready.connect(self.quit_for_update)
        self._timer = QTimer(self)
        self._timer.timeout.connect(lambda: self.check(manual=False))

    def _remember(self, text: str) -> None:
        self.last_status = text

    # ── lifecycle ────────────────────────────────────────────
    def start(self) -> None:
        """Called once the window is up."""
        self._note_version()
        if not installed_build():
            return
        threading.Thread(target=self._tidy, name="update-tidy", daemon=True).start()
        self._timer.start(EVERY_MS)
        QTimer.singleShot(FIRST_CHECK_MS, lambda: self.check(manual=False))

    @staticmethod
    def _tidy() -> None:
        from installer import core, updates
        updates.clean_up()
        core.clean_leftovers()

    def _note_version(self) -> None:
        from config import preferences
        from config.settings import VERSION
        last = str(preferences.get("last_run_version", "") or "")
        if last != VERSION:
            preferences.set_value("last_run_version", VERSION)
            if last:
                QTimer.singleShot(1500, lambda: self.updated.emit(VERSION))

    @property
    def offer(self):
        return self._offer

    # ── checking ─────────────────────────────────────────────
    def check(self, manual: bool = True) -> None:
        if self._busy:
            return
        if not manual:
            from config import preferences
            if not bool(preferences.get("check_updates", True)):
                return
        self._busy = True
        self.status.emit("Checking for updates…")
        threading.Thread(target=self._check, args=(manual,), name="update-check",
                         daemon=True).start()

    def _check(self, manual: bool) -> None:
        from installer import updates
        try:
            found = updates.check()
        except Exception as exc:
            logger.info("Update check failed: %s", exc)
            self.status.emit("Couldn't check for updates — are you online?")
            if manual:
                self.failed.emit("Couldn't reach GitHub to check for updates. "
                                 "Check your connection and try again.")
            return
        finally:
            self._busy = False
        if found is None:
            self.status.emit(f"Mike is up to date ({updates.current_version()}).")
            return
        logger.info("Update available: %s", found.version)
        self._offer = found
        self.status.emit(f"Mike {found.version} is available.")
        self.available.emit(found)

    # ── installing ───────────────────────────────────────────
    def install(self) -> None:
        if self._offer is None or self._busy:
            return
        if not installed_build():
            self.failed.emit("Updating only works in the installed Mike. Download the new "
                             "version from huddlecode.com instead.")
            return
        self._busy = True
        threading.Thread(target=self._install, args=(self._offer,), name="update-install",
                         daemon=True).start()

    def _install(self, offer) -> None:
        from installer import updates

        def on_progress(done: int, total: int) -> None:
            if total:
                pct = int(done * 100 / total)
                self.progress.emit(pct, f"Downloading Mike {offer.version}… {pct}%")

        try:
            self.progress.emit(0, f"Downloading Mike {offer.version}…")
            exe = updates.download(offer, on_progress)
            self.progress.emit(100, "Restarting Mike to finish…")
            updates.hand_over(exe)
        except Exception as exc:
            logger.exception("Update failed")
            self._busy = False
            self.failed.emit(f"The update didn't work: {exc}")
            return
        # The new version waits for this one to quit before it swaps anything.
        self.ready.emit()

    def quit_for_update(self) -> None:
        if callable(self._quit_app):
            self._quit_app()
