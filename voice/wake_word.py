"""Wake-word detection: 'Hey Mike', from anywhere.

The actual mechanism (macOS NSSpeechRecognizer) lives in voice.wake,
alongside whatever platform eventually implements this next. This module
keeps the exact WakeWordDetector name and shape ui_controller.py and the
voice tests already depend on — including `self._on_wake` as a plain,
directly-callable attribute, which a stress test relies on to exercise the
raw callback without going through suppression or the real recognizer.

Construction never raises, on any platform — ui_controller.py constructs
this unconditionally. An OS with no wake-word backend yet is a `.start()`
failure returning False, the same shape a real NSSpeechRecognizer failure
already had, not a startup crash.
"""
from __future__ import annotations

from typing import Callable

from logs.logger import logger
from voice import wake


class WakeWordDetector:
    """Listens for 'Hey Mike'.

    Failure is never fatal — Mike simply has no wake word, and stays
    reachable by the global hotkey and the voice button.
    """

    def __init__(self, on_wake: Callable[[], None]) -> None:
        self._on_wake = on_wake
        self._backend: wake.WakeWordBackend | None = None

    #: True while "Hey Mike" is held back because the microphone is a
    #: Bluetooth headset (Settings explains why).
    paused_for_bluetooth = False

    #: Whether "Hey Mike" is switched on (start() was called, stop() was not).
    #: recheck() only brings it back if it was wanted.
    _wanted = False

    def start(self) -> bool:
        self._wanted = True
        # An always-open microphone on a Bluetooth headset drops the whole
        # headset to phone-call quality for as long as Mike is open -- the
        # music and every video sound muffled and bass-heavy. Wait instead;
        # the mic button and F6 still work (and use the Mac's own microphone).
        from hostplatform import audio
        if audio.default_input_is_bluetooth():
            self.paused_for_bluetooth = True
            logger.info("Wake word not started: the microphone is a Bluetooth headset, "
                        "and listening would degrade its sound.")
            return False
        self.paused_for_bluetooth = False
        if self._backend is None:
            try:
                self._backend = wake.make_backend(self._on_wake)
            except wake.WakeWordUnavailable as exc:
                logger.warning("Wake word unavailable: %s", exc)
                return False
        return self._backend.start()

    def stop(self) -> None:
        self._wanted = False
        self.paused_for_bluetooth = False
        if self._backend is not None:
            self._backend.stop()

    def recheck(self) -> None:
        """Follow the microphone while Mike runs.

        start() only looks once, but headsets come and go: AirPods put in
        after Mike opened become the default microphone, and the recognizer
        follows the default -- dropping them to phone quality. So this is
        called every few seconds: a Bluetooth microphone pauses "Hey Mike",
        and it comes back once the headset is no longer the microphone.
        """
        if not self._wanted:
            return
        from hostplatform import audio
        bluetooth = audio.default_input_is_bluetooth()
        if bluetooth and not self.paused_for_bluetooth:
            if self._backend is not None:
                self._backend.stop()
            self.paused_for_bluetooth = True
            logger.info("Wake word paused: the microphone is now a Bluetooth headset.")
        elif not bluetooth and self.paused_for_bluetooth:
            logger.info("Wake word resuming: the microphone is no longer Bluetooth.")
            self.start()

    def suppress(self) -> None:
        """Suppress detection while Mike is speaking (prevent self-hearing)."""
        if self._backend is not None:
            self._backend.suppress()

    def resume(self) -> None:
        """Resume detection after Mike stops speaking."""
        if self._backend is not None:
            self._backend.resume()

    def take_preroll(self):
        """What was said after "Hey Mike" before the recorder opened, and the
        room's noise level -- (None, None) if nothing is held."""
        if self._backend is None:
            return None, None
        return self._backend.take_preroll()

    @property
    def is_active(self) -> bool:
        return self._backend.is_active if self._backend is not None else False
