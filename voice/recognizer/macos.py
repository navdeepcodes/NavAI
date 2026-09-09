"""macOS speech-to-text backend: SFSpeechRecognizer, on-device.

Thin wrapper around voice/transcriber.py, which holds the actual
implementation. Kept as a separate module rather than moved wholesale: five
test/benchmark scripts import `transcribe_blocking` directly from
voice.transcriber for manual, synchronous use outside Qt's event loop, and
that entry point is unrelated to the pluggable-backend seam this package
exists to provide voice_input.py.
"""
from __future__ import annotations

from typing import Callable

from voice.recognizer.base import SpeechRecognizer


class MacSpeechRecognizer(SpeechRecognizer):

    name = "macos"

    def available(self) -> tuple[bool, str]:
        try:
            from voice.transcriber import _get_recognizer

            recognizer = _get_recognizer()
            if recognizer and recognizer.isAvailable():
                return True, "SFSpeechRecognizer (on-device)"
            return False, "SFSpeechRecognizer is not available on this Mac."
        except Exception as exc:
            return False, f"SFSpeechRecognizer could not be reached: {exc}"

    def transcribe_async(
        self,
        audio_path: str,
        on_done: Callable[[str], None],
        on_error: Callable[[str], None],
    ) -> None:
        from voice.transcriber import transcribe_async

        transcribe_async(audio_path, on_done=on_done, on_error=on_error)
