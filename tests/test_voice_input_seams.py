"""The voice-input seams: speech-to-text and wake-word, apart from the OS.

voice_input.py used to import voice.transcriber (SFSpeechRecognizer) at a
fixed point deep in its state machine — the one hardcoded macOS import
Mike's voice *input* path had, mirroring what voice/providers/ already
solved for voice *output*. This pins the two seams built to fix it:
voice.recognizer for transcription, voice.wake for wake-word detection.

Real construction and real registration on whichever platform provides a
backend; a named, explained exception — never a silent stub — on one that
doesn't yet.
"""
from __future__ import annotations

import os
import platform
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401

import pytest


# ── speech-to-text ──────────────────────────────────────────

@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS-only backend")
def test_get_recognizer_returns_a_real_macos_backend():
    from voice.recognizer import get_recognizer
    from voice.recognizer.macos import MacSpeechRecognizer

    recognizer = get_recognizer()
    assert isinstance(recognizer, MacSpeechRecognizer)
    ok, why = recognizer.available()
    assert isinstance(ok, bool) and isinstance(why, str) and why


@pytest.mark.skipif(platform.system() != "Windows", reason="Windows-only backend")
def test_get_recognizer_returns_a_real_windows_backend():
    from voice.recognizer import get_recognizer
    from voice.recognizer.windows import WhisperRecognizer

    recognizer = get_recognizer()
    assert isinstance(recognizer, WhisperRecognizer)
    ok, why = recognizer.available()
    assert isinstance(ok, bool) and isinstance(why, str) and why


@pytest.mark.skipif(platform.system() != "Windows", reason="Windows-only backend")
def test_whisper_recognizer_transcribes_real_audio_end_to_end():
    """Not mocked: loads the real model and runs it against a real recorded
    WAV (audio/recordings/recording.wav, a genuine prior mic capture saying
    "one two three mic testing"), on a background thread, exactly as
    voice_input.py drives it. Pins the whole local pipeline -- model load,
    inference, and the off-thread on_done callback -- not just that the
    class satisfies the interface."""
    import threading
    from pathlib import Path

    from voice.recognizer.windows import WhisperRecognizer

    audio_path = Path(__file__).resolve().parent.parent / "audio" / "recordings" / "recording.wav"
    if not audio_path.exists():
        pytest.skip("no real recorded fixture on this checkout")

    recognizer = WhisperRecognizer()
    ok, _why = recognizer.available()
    assert ok

    done = threading.Event()
    result: dict = {}

    def on_done(text: str) -> None:
        result["text"] = text
        done.set()

    def on_error(message: str) -> None:
        result["error"] = message
        done.set()

    recognizer.transcribe_async(str(audio_path), on_done=on_done, on_error=on_error)
    assert done.wait(timeout=600), "transcription did not complete in time"

    assert "error" not in result, result.get("error")
    assert "mic" in result["text"].lower() or "testing" in result["text"].lower(), result["text"]


def test_get_recognizer_raises_a_named_error_for_an_unsupported_platform(monkeypatch):
    import voice.recognizer as recognizer_module

    recognizer_module._instance = None
    monkeypatch.setattr(recognizer_module.platform, "system", lambda: "Plan9")
    with pytest.raises(recognizer_module.RecognizerUnavailable):
        recognizer_module.get_recognizer()
    recognizer_module._instance = None


def test_voice_input_falls_back_to_an_error_rather_than_crashing(monkeypatch):
    """The exact failure mode voice_input.py hits on a platform with no
    recognizer: an error signal, not an unhandled exception mid-turn."""
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication(sys.argv)

    from voice.voice_input import VoiceInputManager

    manager = VoiceInputManager()
    errors: list[str] = []
    manager.error.connect(errors.append)

    import voice.recognizer as recognizer_module

    def _boom():
        raise recognizer_module.RecognizerUnavailable("no backend on this OS")

    monkeypatch.setattr(recognizer_module, "get_recognizer", _boom)

    manager._state = "recording"
    monkeypatch.setattr(manager._recorder, "stop", lambda: "/tmp/does-not-matter.wav")
    manager._stop_and_transcribe()

    assert manager.state == "idle"
    assert errors and "no backend on this OS" in errors[0]


# ── wake word ───────────────────────────────────────────────

@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS-only backend")
def test_make_backend_returns_a_real_macos_backend():
    from voice.wake import make_backend
    from voice.wake.macos import MacWakeWord

    backend = make_backend(lambda: None)
    assert isinstance(backend, MacWakeWord)
    assert not backend.is_active


@pytest.mark.skipif(platform.system() != "Windows", reason="Windows-only backend")
def test_make_backend_returns_a_real_windows_backend():
    """The regression this guards: Windows used to raise WakeWordUnavailable
    from make_backend, so 'Hey Mike' and voice barge-in did not exist on
    Windows at all. It now returns a real always-on backend."""
    from voice.wake import make_backend
    from voice.wake.windows import WindowsWakeWord

    backend = make_backend(lambda: None)
    assert isinstance(backend, WindowsWakeWord)
    assert not backend.is_active


def test_windows_wake_matches_the_name_not_common_lookalikes():
    """Pure logic, so it runs anywhere: the matcher fires on the name and its
    plausible transcriptions but not on words that merely contain it, because
    a wake word that trips on 'microphone' is worse than none."""
    from voice.wake.windows import WindowsWakeWord as W

    assert W._is_wake("hey mike are you there")
    assert W._is_wake("okay mike")
    assert W._is_wake("hey mikey")
    assert not W._is_wake("turn on the microphone")
    assert not W._is_wake("mic check one two")
    assert not W._is_wake("i talked to michael")
    assert not W._is_wake("")


def test_make_backend_raises_a_named_error_for_an_unsupported_platform(monkeypatch):
    import voice.wake as wake_module

    monkeypatch.setattr(wake_module.platform, "system", lambda: "Plan9")
    with pytest.raises(wake_module.WakeWordUnavailable):
        wake_module.make_backend(lambda: None)


def test_wake_word_detector_start_fails_cleanly_with_no_backend(monkeypatch):
    """The façade's own contract: an unavailable backend is a False from
    start(), never a raised exception reaching ui_controller.py."""
    from voice.wake_word import WakeWordDetector
    import voice.wake as wake_module

    def _boom(_on_wake):
        raise wake_module.WakeWordUnavailable("no backend on this OS")

    monkeypatch.setattr(wake_module, "make_backend", _boom)

    detector = WakeWordDetector(on_wake=lambda: None)
    assert detector.start() is False
    assert not detector.is_active
    detector.stop()           # must not raise with no backend ever built
    detector.suppress()
    detector.resume()


if __name__ == "__main__":
    if platform.system() == "Darwin":
        test_get_recognizer_returns_a_real_macos_backend()
        test_make_backend_returns_a_real_macos_backend()
    if platform.system() == "Windows":
        test_get_recognizer_returns_a_real_windows_backend()
        test_whisper_recognizer_transcribes_real_audio_end_to_end()
    print("\nAll voice-input-seam tests passed.")
