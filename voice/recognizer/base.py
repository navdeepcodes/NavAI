"""What Mike needs from speech-to-text, independent of who provides it.

Mirrors voice/providers/base.py's VoiceProvider contract, but for the input
side: Mike Core only needs "transcribe this audio, call me back with the
text" — SFSpeechRecognizer on macOS, and eventually something else, are the
adapter's business, not voice/voice_input.py's.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable


class SpeechRecognizer(ABC):
    """One way of turning recorded speech into text."""

    #: Shown in logs. Stable, lowercase, no spaces.
    name: str = "unnamed"

    @abstractmethod
    def available(self) -> tuple[bool, str]:
        """Can this backend transcribe right now, and if not, why not?"""

    @abstractmethod
    def transcribe_async(
        self,
        audio_path: str,
        on_done: Callable[[str], None],
        on_error: Callable[[str], None],
    ) -> None:
        """Begin transcribing a WAV file.

        Must not block — this is called from voice_input.py's Qt-thread
        state machine, and anything it waits for is time the interface is
        frozen. Exactly one of `on_done`/`on_error` fires, later, on
        whatever thread or run loop the backend uses.
        """
