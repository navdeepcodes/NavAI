"""Run Python's cyclic garbage collector only on the GUI thread.

Python's automatic GC runs on whichever thread happens to allocate past the
threshold. Mike has many busy background threads — the wake-word loop
transcribing every 0.7s, Piper's reader/synth/playback threads, the model
warm-up, speech-to-text, the turn workers — so a collection regularly fires on
one of them. If that collection finalises a Qt object (a widget or timer that
ended up in a reference cycle), Qt destroys it on the wrong thread and the
process dies with an access violation: a random, unreproducible crash.

Found in the production-readiness pass as a hard crash: "Windows fatal
exception: access violation — Garbage-collecting", inside a background thread
importing faster-whisper.

The fix is the standard one for threaded PySide apps: turn automatic
collection off and collect from a timer on the GUI thread, using the same
generation thresholds, so memory is reclaimed just as before — only ever on
the thread that owns the Qt objects.
"""
from __future__ import annotations

import gc

from PySide6.QtCore import QObject, QTimer

from logs.logger import logger


class MainThreadGC(QObject):
    """Collect garbage on the GUI thread instead of wherever it happens."""

    INTERVAL_MS = 500

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._threshold = gc.get_threshold()
        gc.disable()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.check)
        self._timer.start(self.INTERVAL_MS)

    def check(self) -> None:
        try:
            l0, l1, l2 = gc.get_count()
            if l0 > self._threshold[0]:
                gc.collect(0)
                if l1 > self._threshold[1]:
                    gc.collect(1)
                    if l2 > self._threshold[2]:
                        gc.collect(2)
        except Exception:
            logger.debug("Main-thread garbage collection failed.", exc_info=True)

    def stop(self) -> None:
        self._timer.stop()
        gc.enable()
