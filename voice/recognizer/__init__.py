"""The speech-to-text backend for this machine.

voice_input.py used to import voice.transcriber (SFSpeechRecognizer)
directly, deep inside its state machine — the one hardcoded macOS import
this repo's voice *input* path had, mirroring the same shape voice/providers
already solved for voice *output*. get_recognizer() is that same seam for
the input side.
"""
from __future__ import annotations

import platform

from voice.recognizer.base import SpeechRecognizer

_instance: SpeechRecognizer | None = None


class RecognizerUnavailable(Exception):
    """No speech-to-text backend exists for this platform yet."""


def get_recognizer() -> SpeechRecognizer:
    """The one recognizer for this machine, constructed once and reused.

    Raises RecognizerUnavailable rather than returning a stub — the caller
    (voice_input.py) treats that like any other transcription failure: the
    user hears "transcription failed: ..." rather than silence, and never a
    fabricated success.
    """
    global _instance
    if _instance is not None:
        return _instance

    system = platform.system()
    if system == "Darwin":
        from voice.recognizer.macos import MacSpeechRecognizer

        _instance = MacSpeechRecognizer()
        return _instance
    if system == "Windows":
        raise RecognizerUnavailable(
            "No speech-to-text backend for Windows yet. SFSpeechRecognizer "
            "has no direct Windows equivalent; a real implementation needs "
            "either a local model (e.g. Whisper) or the Windows Speech "
            "Recognition API, chosen and verified on the physical machine "
            "rather than added as a guessed dependency."
        )
    raise RecognizerUnavailable(f"No speech-to-text backend for {system}.")
