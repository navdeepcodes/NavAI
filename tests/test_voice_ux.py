"""Tests for Voice UX v2: auto-stop, silence detection, wake word, states."""
from __future__ import annotations

import os
import sys
import time
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401 — must run before any brain/config import

import numpy as np


def test_silence_detection_constants():
    """
    Verify silence detection constants are sensible. Recorder switched from
    a single fixed SPEECH_RMS_THRESHOLD to a per-recording calibrated
    threshold (floor + multiplier over a measured noise floor) — this test
    had gone stale against that change, still asserting on a constant that
    no longer exists, so it always failed even though the real code was
    fine. Updated to check the constants that replaced it.
    """
    from voice.recorder import (
        CALIBRATION_SECONDS,
        THRESHOLD_MULTIPLIER,
        THRESHOLD_FLOOR,
        SILENCE_DURATION,
        MIN_SPEECH_DURATION,
        MAX_RECORDING,
    )
    assert 0.1 <= CALIBRATION_SECONDS <= 1.0
    assert 1.5 <= THRESHOLD_MULTIPLIER <= 5.0
    assert 0.001 < THRESHOLD_FLOOR < 0.02
    assert 0.5 <= SILENCE_DURATION <= 3.0
    assert 0.2 <= MIN_SPEECH_DURATION <= 1.0
    assert 15 <= MAX_RECORDING <= 120
    print(f"PASS: silence constants (calibration={CALIBRATION_SECONDS}s, "
          f"multiplier={THRESHOLD_MULTIPLIER}, floor={THRESHOLD_FLOOR}, "
          f"dur={SILENCE_DURATION}s, min_speech={MIN_SPEECH_DURATION}s, "
          f"max={MAX_RECORDING}s)")


def test_recorder_auto_stop_flag():
    """Verify auto-stop flag works."""
    from voice.recorder import PushToTalkRecorder

    rec = PushToTalkRecorder()
    ok = rec.start()
    assert ok
    assert rec.is_recording
    assert not rec.should_auto_stop

    rec.stop()
    assert not rec.is_recording
    print("PASS: recorder has auto-stop flag")


def test_recorder_max_duration():
    """Verify MAX_RECORDING prevents runaway recording."""
    from voice.recorder import MAX_RECORDING
    assert MAX_RECORDING == 30
    print(f"PASS: max recording duration = {MAX_RECORDING}s")


def test_voice_manager_auto_stop_signal():
    """VoiceInputManager has auto_stopped signal."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)

    from voice.voice_input import VoiceInputManager
    mgr = VoiceInputManager()
    assert hasattr(mgr, 'auto_stopped')
    assert hasattr(mgr, 'start_recording')
    assert hasattr(mgr, 'stop_recording')
    print("PASS: VoiceInputManager has auto-stop API")


def test_voice_button_speaking_state():
    """The live UI signals voice state through the Instrument dial, not an
    emoji button.

    This previously asserted `btn.text() == "🔊"` against
    ui.widgets.input.VoiceButton, which the current app no longer uses — the
    Instrument surfaces replaced it and nothing in ui/instrument, ui/app.py or
    the controller references that widget. Rewritten against the surface the
    controller actually drives, so it tests shipped behaviour rather than a
    retired widget.
    """
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841

    from ui.instrument.home import HomeSurface

    page = HomeSurface({})

    # These are the exact states UIController pushes through .input.voice.
    page.input.voice.set_state("recording")
    assert page.input.dial.state() == "listening"

    page.input.voice.set_state("transcribing")
    assert page.input.dial.state() == "thinking"

    page.input.voice.set_state("speaking")
    assert page.input.dial.state() == "responding"

    print("PASS: voice state reaches the live dial")


def test_wake_word_detector_import():
    """WakeWordDetector creates without error."""
    from voice.wake_word import WakeWordDetector

    triggered = {"count": 0}

    def on_wake():
        triggered["count"] += 1

    det = WakeWordDetector(on_wake=on_wake)
    assert not det.is_active
    print("PASS: WakeWordDetector created")


def test_wake_word_suppress_resume():
    """WakeWordDetector suppress/resume API works."""
    from voice.wake_word import WakeWordDetector

    det = WakeWordDetector(on_wake=lambda: None)
    det.suppress()
    det.resume()
    print("PASS: wake word suppress/resume (not started)")


def test_wake_word_start_stop():
    """WakeWordDetector starts and stops cleanly."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)

    from voice.wake_word import WakeWordDetector

    det = WakeWordDetector(on_wake=lambda: None)
    started = det.start()
    if started:
        assert det.is_active
        det.suppress()
        det.resume()
        det.stop()
        assert not det.is_active
        print("PASS: wake word start/stop lifecycle")
    else:
        print("PASS: wake word not available (NSSpeechRecognizer unavailable)")


def test_controller_has_voice_shortcut():
    """UIController exposes voice_shortcut_pressed."""
    from ui.controller.ui_controller import UIController
    assert hasattr(UIController, 'voice_shortcut_pressed')
    print("PASS: controller has voice_shortcut_pressed")


def test_app_has_capslock_handler():
    """MikeWindow handles CapsLock key."""
    from ui.app import MikeWindow
    assert hasattr(MikeWindow, 'keyPressEvent')
    print("PASS: MikeWindow has keyPressEvent for CapsLock")


if __name__ == "__main__":
    test_silence_detection_constants()
    test_recorder_auto_stop_flag()
    test_recorder_max_duration()
    test_voice_manager_auto_stop_signal()
    test_voice_button_speaking_state()
    test_wake_word_detector_import()
    test_wake_word_suppress_resume()
    test_wake_word_start_stop()
    test_controller_has_voice_shortcut()
    test_app_has_capslock_handler()
    print("\nAll Voice UX v2 tests passed.")
