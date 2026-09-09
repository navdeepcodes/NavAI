"""What Mike needs from a wake-word backend, independent of who implements it.

Mirrors voice/providers/base.py's VoiceProvider contract, and
voice/recognizer/base.py's for transcription: Mike Core only needs "listen
for the wake phrase, call me back" — NSSpeechRecognizer today, and
eventually something else, are the adapter's business.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class WakeWordBackend(ABC):
    """One way of listening for Mike's wake phrase."""

    @abstractmethod
    def start(self) -> bool:
        """Begin listening. False means it could not start — never raises."""

    @abstractmethod
    def stop(self) -> None:
        """Stop listening and release everything held."""

    @abstractmethod
    def suppress(self) -> None:
        """Pause listening without a full stop — used while Mike is
        speaking, so he does not hear himself say the wake phrase."""

    @abstractmethod
    def resume(self) -> None:
        """Undo suppress()."""

    @property
    @abstractmethod
    def is_active(self) -> bool:
        ...
