"""Unit tests for voice input components."""
from __future__ import annotations

import os
import platform
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


def test_recorder_start_stop():
    """Test recorder starts and stops without crashing."""
    from voice.recorder import PushToTalkRecorder

    rec = PushToTalkRecorder()
    assert not rec.is_recording

    ok = rec.start()
    assert ok
    assert rec.is_recording

    time.sleep(0.5)

    path = rec.stop()
    assert not rec.is_recording
    # path may be None if too quiet — that's OK for unit test
    print("PASS: recorder start/stop")


def test_recorder_double_start():
    """Can't start twice."""
    from voice.recorder import PushToTalkRecorder

    rec = PushToTalkRecorder()
    rec.start()
    assert not rec.start()  # second start returns False
    rec.stop()
    print("PASS: recorder double-start blocked")


def test_recorder_stop_without_start():
    """Stopping without starting returns None."""
    from voice.recorder import PushToTalkRecorder

    rec = PushToTalkRecorder()
    assert rec.stop() is None
    print("PASS: recorder stop-without-start")


@pytest.mark.skipif(
    platform.system() != "Darwin",
    reason="voice.transcriber is the macOS SFSpeechRecognizer backend; "
           "Windows transcription is voice.recognizer.windows.WhisperRecognizer, "
           "covered by tests/test_voice_input_seams.py",
)
def test_transcribe_missing_file():
    """Transcribing a missing file returns empty string."""
    from voice.transcriber import transcribe_blocking

    text = transcribe_blocking("/nonexistent/audio.wav")
    assert text == ""
    print("PASS: transcribe missing file")


def test_transcribe_synthesized():
    """Transcribe macOS-generated speech."""
    wav_path = "/tmp/test_voice_unit.wav"
    os.system(
        f'say -o /tmp/test_voice_unit.aiff "Hello world" && '
        f'afconvert -f WAVE -d LEI16 /tmp/test_voice_unit.aiff {wav_path}'
    )
    if not os.path.exists(wav_path):
        print("SKIP: could not generate test audio")
        return

    from voice.transcriber import transcribe_blocking

    text = transcribe_blocking(wav_path)
    assert "hello" in text.lower(), f"Expected 'hello' in '{text}'"
    print(f"PASS: transcribe synthesized speech -> '{text}'")
    os.unlink(wav_path)
    os.unlink("/tmp/test_voice_unit.aiff")


def test_voice_manager_import():
    """VoiceInputManager creates without error."""
    from voice.voice_input import VoiceInputManager

    mgr = VoiceInputManager()
    assert mgr.state == "idle"
    print("PASS: VoiceInputManager created")


if __name__ == "__main__":
    test_recorder_start_stop()
    test_recorder_double_start()
    test_recorder_stop_without_start()
    test_transcribe_missing_file()
    test_transcribe_synthesized()
    test_voice_manager_import()
    print("\nAll voice unit tests passed.")
