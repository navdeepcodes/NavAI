"""macOS wake-word detection using NSSpeechRecognizer.

NSSpeechRecognizer is a lightweight command-and-control recognizer designed
for keyword spotting — minimal CPU, entirely on-device. Moved here from
voice/wake_word.py, which is now the platform-independent façade
ui_controller.py and the voice tests import.
"""
from __future__ import annotations

from typing import Callable

import objc
from Foundation import NSObject

from logs.logger import logger
from voice.wake.base import WakeWordBackend

WAKE_PHRASES = ["Hey Mike", "Hey mike", "hey Mike", "hey mike"]


class _WakeWordDelegate(NSObject):

    def initWithCallback_(self, callback: Callable[[], None]):
        self = objc.super(_WakeWordDelegate, self).init()
        if self is None:
            return None
        self._callback = callback
        return self

    def speechRecognizer_didRecognizeCommand_(self, sender, command):
        logger.info("Wake word detected: %s", command)
        if self._callback:
            self._callback()


class MacWakeWord(WakeWordBackend):

    def __init__(self, on_wake: Callable[[], None]) -> None:
        self._on_wake = on_wake
        self._recognizer = None
        self._delegate = None
        self._active = False
        self._suppressed = False

    def start(self) -> bool:
        if self._active:
            return True

        try:
            import AppKit
            self._recognizer = AppKit.NSSpeechRecognizer.alloc().init()
            if self._recognizer is None:
                logger.error("NSSpeechRecognizer not available")
                return False

            self._delegate = _WakeWordDelegate.alloc().initWithCallback_(
                self._handle_wake
            )
            self._recognizer.setCommands_(WAKE_PHRASES)
            self._recognizer.setListensInForegroundOnly_(False)
            self._recognizer.setDelegate_(self._delegate)
            self._recognizer.startListening()
            self._active = True
            logger.info("Wake word detector started")
            return True
        except Exception as exc:
            logger.exception("Failed to start wake word detector: %s", exc)
            return False

    def stop(self) -> None:
        if self._recognizer is not None:
            self._recognizer.stopListening()
            self._recognizer.setDelegate_(None)
            self._recognizer = None
            self._delegate = None
        self._active = False
        logger.info("Wake word detector stopped")

    def suppress(self) -> None:
        """Suppress detection while Mike is speaking (prevent self-hearing)."""
        if self._active and self._recognizer and not self._suppressed:
            self._recognizer.stopListening()
            self._suppressed = True

    def resume(self) -> None:
        """Resume detection after Mike stops speaking."""
        if self._active and self._recognizer and self._suppressed:
            self._recognizer.startListening()
            self._suppressed = False

    @property
    def is_active(self) -> bool:
        return self._active

    def _handle_wake(self) -> None:
        if self._suppressed:
            return
        try:
            self._on_wake()
        except Exception:
            # The real ObjC delegate call site. This used to call the
            # callback with nothing to catch an exception -- one bug in
            # Mike's own wake-word handler could have propagated back through
            # the Objective-C bridge uncaught. The façade's own `_on_wake`
            # attribute (voice/wake_word.py) stays the raw, unwrapped
            # callback for tests that exercise it directly; this is the only
            # call site that goes through the real recognizer.
            logger.exception("Wake word callback failed.")
