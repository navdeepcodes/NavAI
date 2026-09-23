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

    def prewarm(self) -> None:
        """Do the slow one-time setup now, off the path a user is waiting on.

        Default: nothing. A backend that loads or downloads a model the first
        time it transcribes overrides this so that cost is paid at startup —
        while the greeting is on screen — instead of freezing the very first
        spoken turn. Must never raise; a failed prewarm just means the first
        real transcription pays what it would have anyway.
        """

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
