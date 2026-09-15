"""Local wake-word detection.

macOS uses NSSpeechRecognizer, a lightweight on-device command-and-control
recognizer built for exactly this (keyword spotting, minimal CPU).

Linux has no equivalent shipped with the OS — there is no built-in
low-power keyword spotter comparable to NSSpeechRecognizer, and pulling in
an offline engine (e.g. a Porcupine/Vosk keyword model) is a real feature,
not a compatibility shim, so it isn't faked here. WakeWordDetector.start()
returns False and logs why; callers already treat a False return as
"wake word unavailable" (see ui/app.py), so the rest of Mike degrades
gracefully to push-to-talk instead of crashing or silently doing nothing.
"""
from __future__ import annotations

from typing import Callable

from hostplatform import is_macos
from logs.logger import logger

WAKE_PHRASES = ["Hey Mike", "Hey mike", "hey Mike", "hey mike"]


class WakeWordDetector:

    def __init__(self, on_wake: Callable[[], None]) -> None:
        self._on_wake = on_wake
        self._recognizer = None
        self._delegate = None
        self._active = False
        self._suppressed = False

    def start(self) -> bool:
        if self._active:
            return True

        if not is_macos():
            logger.warning(
                "Wake word detection is not implemented on this platform yet "
                "(no on-device keyword spotter wired up). Use push-to-talk instead."
            )
            return False

        try:
            import objc
            import AppKit
            from Foundation import NSObject

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
        if not self._suppressed:
            self._on_wake()
