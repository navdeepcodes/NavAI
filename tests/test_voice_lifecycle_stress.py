"""Stressing voice and background lifecycle, rather than inheriting coverage.

The existing lifecycle tests prove the contract once: close hides, quit tears
down. This file asks the questions that only repetition and failure answer.

  * Does the tenth start/stop cycle behave like the first, or do threads,
    hotkey registrations and audio streams accumulate?
  * Can speech be interrupted mid-utterance, which is what barge-in is?
  * And the one that matters most: **can a voice or background failure take
    the core runtime with it?** Mike's whole value is that it keeps working;
    a microphone that throws, a TTS binary that is missing, or a wake-word
    callback that raises must be a degraded ear, not a dead assistant.

Real objects throughout — real Speaker driving the real `say` binary, real
recorder, real MikeWindow with real hotkey registration and a real IDE bridge
socket. The wake word is disabled through the ordinary preference so these
stay off the microphone permission prompt, and its own lifecycle is stressed
separately below.
"""
from __future__ import annotations

import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401 — must run before any brain/config import

import pytest


def _app():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication(sys.argv)


def _fresh_window():
    from config import preferences

    preferences.set_value("wake_word_enabled", False)
    from ui.app import MikeWindow

    return MikeWindow()


# ══ repeated startup and shutdown ══════════════════════════

def test_five_startup_shutdown_cycles_leave_nothing_behind():
    """A leak shows up on the fifth cycle, not the first. Threads are counted
    around the whole sequence: a hotkey that fails to unregister or a worker
    thread that outlives its window would show here as a rising count."""
    _app()

    from ide import manager as ide_manager

    before = threading.active_count()

    for cycle in range(5):
        window = _fresh_window()
        window.show()

        assert window.hotkey._registered, f"cycle {cycle}: hotkey did not register"
        assert ide_manager._started, f"cycle {cycle}: IDE bridge did not start"

        window._teardown()

        assert window._torn_down
        assert not window.hotkey._registered, f"cycle {cycle}: hotkey left registered"
        assert not ide_manager._started, f"cycle {cycle}: IDE bridge left running"
        assert window.controller._thread is None, f"cycle {cycle}: thread orphaned"
        assert not window.controller._retired_threads, f"cycle {cycle}: retired thread kept"

    # Qt keeps a few internal threads; the check is that the count did not
    # climb with the cycles.
    after = threading.active_count()
    assert after <= before + 2, (
        f"threads grew from {before} to {after} across five cycles — something "
        "is not being torn down"
    )


def test_teardown_is_safe_to_repeat_many_times():
    _app()
    window = _fresh_window()
    for _ in range(5):
        window._teardown()
    assert window._torn_down


def test_hide_and_show_repeatedly_keeps_every_service_alive():
    """Hiding is the ordinary thing a person does all day. Doing it twenty
    times must not degrade anything."""
    _app()

    from ide import manager as ide_manager

    window = _fresh_window()
    try:
        for _ in range(20):
            window.show()
            window.hide()
        assert window.hotkey._registered
        assert ide_manager._started
        assert window.tray.isVisible()
    finally:
        window._teardown()


# ══ wake word ══════════════════════════════════════════════

def test_wake_word_survives_ten_start_stop_cycles():
    _app()

    from voice.wake_word import WakeWordDetector

    fired = []
    detector = WakeWordDetector(on_wake=lambda: fired.append(1))

    available = detector.start()
    if not available:
        pytest.skip("NSSpeechRecognizer is unavailable on this machine")

    try:
        for cycle in range(10):
            assert detector.is_active, f"cycle {cycle}: not active after start"
            detector.suppress()
            detector.resume()
            detector.stop()
            assert not detector.is_active, f"cycle {cycle}: still active after stop"
            detector.start()
    finally:
        detector.stop()


def test_suppress_and_resume_are_safe_before_starting():
    """Called from the controller whenever Mike speaks, which can happen
    before the detector has ever started."""
    from voice.wake_word import WakeWordDetector

    detector = WakeWordDetector(on_wake=lambda: None)
    for _ in range(5):
        detector.suppress()
        detector.resume()
    detector.stop()


def test_a_wake_word_callback_that_raises_does_not_kill_the_detector():
    """The callback runs Mike's own code. If a bug in it could stop the
    detector, one bad turn would silently end voice for the whole session."""
    _app()

    from voice.wake_word import WakeWordDetector

    calls = []

    def exploding():
        calls.append(1)
        raise RuntimeError("deliberate failure inside the wake callback")

    detector = WakeWordDetector(on_wake=exploding)
    if not detector.start():
        pytest.skip("NSSpeechRecognizer is unavailable on this machine")

    try:
        for _ in range(3):
            try:
                detector._on_wake()
            except RuntimeError:
                # Raising out of the callback is acceptable; dying is not.
                pass
        assert detector.is_active, "the detector stopped because the callback raised"
        assert len(calls) == 3
    finally:
        detector.stop()


# ══ recording ══════════════════════════════════════════════

def test_ten_record_cycles_do_not_leak_streams():
    from voice.recorder import PushToTalkRecorder

    recorder = PushToTalkRecorder()
    for cycle in range(10):
        assert recorder.start(), f"cycle {cycle}: recorder refused to start"
        assert recorder.is_recording
        time.sleep(0.05)
        recorder.stop()
        assert not recorder.is_recording, f"cycle {cycle}: still recording after stop"


def test_stopping_a_recorder_that_never_started_is_harmless():
    from voice.recorder import PushToTalkRecorder

    recorder = PushToTalkRecorder()
    for _ in range(3):
        recorder.stop()
    assert not recorder.is_recording


def test_starting_twice_does_not_produce_two_streams():
    from voice.recorder import PushToTalkRecorder

    recorder = PushToTalkRecorder()
    recorder.start()
    recorder.start()
    recorder.stop()
    assert not recorder.is_recording


# ══ speech, and interrupting it ════════════════════════════

def test_speech_can_be_interrupted_mid_utterance():
    """Barge-in. A long sentence is started and stopped almost immediately;
    the process must actually be gone, not merely marked as gone."""
    from voice.speaker import Speaker

    speaker = Speaker()
    speaker.speak(
        "This is a deliberately long sentence which should be cut off well "
        "before it reaches the end, because the user has started talking."
    )
    time.sleep(0.35)
    assert speaker.is_speaking(), "nothing was speaking, so nothing was interrupted"

    speaker.stop()

    assert not speaker.is_speaking()
    # The process now belongs to the provider rather than to Speaker. The
    # guarantee is the same one, checked where the process actually lives.
    assert speaker._native._process is None, "the say process was left behind"


def test_a_new_utterance_replaces_the_one_in_progress():
    """Speaking again while speaking is the ordinary interruption path: the
    old audio has to stop, or two voices talk over each other."""
    from voice.speaker import Speaker

    speaker = Speaker()
    speaker.speak("The first sentence, which is quite long and will be cut off.")
    time.sleep(0.3)
    first = speaker._native._process
    assert first is not None

    speaker.speak("The second sentence.")
    assert speaker._native._process is not first
    assert first.poll() is not None, "the first utterance was left running"
    speaker.stop()


def test_streaming_speech_drains_and_stops():
    from voice.speaker import Speaker

    speaker = Speaker()
    for sentence in ("One.", "Two.", "Three."):
        speaker.speak_sentence(sentence)
    speaker.finish_streaming()

    speaker.stop()
    assert speaker.streaming_done
    assert not speaker.is_speaking()
    assert speaker._queue == []


def test_stop_is_safe_when_nothing_is_speaking():
    from voice.speaker import Speaker

    speaker = Speaker()
    for _ in range(5):
        speaker.stop()
    assert not speaker.is_speaking()


def test_twenty_speak_stop_cycles_leave_no_processes():
    """Each utterance is a subprocess. Twenty rapid cycles would show up as
    zombies if stop() were not really reaping them."""
    from voice.speaker import Speaker

    speaker = Speaker()
    processes = []
    for _ in range(20):
        speaker.speak("Testing one two three.")
        if speaker._native._process:
            processes.append(speaker._native._process)
        speaker.stop()

    assert not speaker.is_speaking()
    time.sleep(0.2)
    alive = [p for p in processes if p.poll() is None]
    assert not alive, f"{len(alive)} say processes were left running"


# ══ failure isolation: the point of the whole file ═════════

def test_a_broken_speaker_does_not_stop_the_runtime():
    """TTS is an output device. If the machine has no `say`, or it fails, Mike
    must still think and act — the answer simply arrives silently."""
    from brain.core_runtime import CoreRuntime
    from voice.speaker import Speaker

    speaker = Speaker()
    original = __import__("subprocess").Popen

    import subprocess as sp

    def refuse(*args, **kwargs):
        raise OSError("no such binary: say")

    sp.Popen = refuse
    try:
        speaker.speak("this cannot be spoken")   # must not raise
        assert not speaker.is_speaking()
    finally:
        sp.Popen = original

    runtime = CoreRuntime()
    result = runtime._execute_tool("calculate", {"expression": "2 + 2"})
    assert result["status"] == "success", "the runtime died with the speaker"


def test_a_microphone_failure_does_not_stop_the_runtime():
    from brain.core_runtime import CoreRuntime
    from voice.recorder import PushToTalkRecorder

    recorder = PushToTalkRecorder()

    import sounddevice

    original = sounddevice.InputStream

    def refuse(*args, **kwargs):
        raise RuntimeError("no input device available")

    sounddevice.InputStream = refuse
    try:
        started = recorder.start()
        assert started is False, "a dead microphone must be reported, not pretended"
        assert not recorder.is_recording
    finally:
        sounddevice.InputStream = original

    runtime = CoreRuntime()
    result = runtime._execute_tool("calculate", {"expression": "40 + 2"})
    assert result["status"] == "success", "the runtime died with the microphone"


def test_transcription_of_a_missing_file_is_reported_not_raised():
    """Speech recognition is fed a file the recorder wrote. If that write
    failed, transcription must come back empty rather than throwing into the
    voice thread and taking the turn with it."""
    from voice.transcriber import transcribe_blocking

    result = transcribe_blocking("/nonexistent/definitely-not-here.wav", timeout=3.0)
    assert result == "" or isinstance(result, str)


def test_transcription_of_a_real_recording_returns_text():
    """The recognition path itself, end to end, on audio this test makes."""
    import subprocess
    import tempfile
    from pathlib import Path

    from voice.transcriber import transcribe_blocking

    wav = Path(tempfile.mkdtemp()) / "spoken.wav"
    made = subprocess.run(
        ["say", "-o", str(wav), "--data-format=LEI16@16000",
         "testing one two three"],
        capture_output=True,
    )
    if made.returncode != 0 or not wav.exists():
        pytest.skip("the say binary could not produce a recording")

    text = transcribe_blocking(str(wav), timeout=20.0)
    if not text:
        pytest.skip("speech recognition is unavailable or not permitted here")
    assert isinstance(text, str) and text.strip()
    print(f"recognised: {text!r}")


def test_the_window_survives_a_service_that_fails_to_start():
    """A background service failing at startup must degrade that service, not
    prevent Mike from opening."""
    _app()

    from ide import manager as ide_manager

    original = ide_manager.start

    def refuse(*args, **kwargs):
        raise RuntimeError("port already in use")

    ide_manager.start = refuse
    try:
        try:
            window = _fresh_window()
        except Exception as exc:
            pytest.fail(
                f"a failing IDE bridge prevented Mike from opening: "
                f"{type(exc).__name__}: {exc}"
            )
    finally:
        ide_manager.start = original

    try:
        assert window.isEnabled()
        assert window.controller is not None, "the controller must still exist"
    finally:
        window._teardown()


def test_a_failing_hotkey_registration_does_not_prevent_mike_from_opening():
    """Same guarantee for the other optional service started in __init__.
    Losing a keyboard shortcut is an inconvenience; losing Mike because of
    one is not."""
    _app()

    from ui.system.global_hotkey import GlobalHotkey

    original = GlobalHotkey.register

    def refuse(self):
        raise RuntimeError("Carbon refused the hotkey")

    GlobalHotkey.register = refuse
    try:
        window = _fresh_window()
    except Exception as exc:
        pytest.fail(f"a failing hotkey prevented Mike from opening: {exc}")
    finally:
        GlobalHotkey.register = original

    try:
        assert window.controller is not None
        assert window.tray.isVisible(), "the tray must still be there to reopen Mike"
    finally:
        window._teardown()
