"""Opening the microphone on a Bluetooth headset ruins its sound.

Measured: with Mike open and "Hey Mike" listening, a headset's output fell from
44,100 Hz to 16,000 Hz (phone-call mode: muffled, thin, bass-heavy) and came
back the moment Mike quit. So when the default microphone is Bluetooth, the
always-on wake word must wait and recording must use the computer's own mic.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401

from hostplatform import audio

DEVICES = [
    {"name": "MacBook Air Microphone", "max_input_channels": 1},   # 0 built-in
    {"name": "MacBook Air Speakers", "max_input_channels": 0},     # 1 output only
    {"name": "HBTS003", "max_input_channels": 1},                  # 2 bluetooth in
    {"name": "HBTS003", "max_input_channels": 0},                  # 3 bluetooth out
]


# ── detecting Bluetooth ───────────────────────────────────────

def test_bluetooth_is_recognised_by_transport_type(monkeypatch):
    monkeypatch.setattr(audio.platform, "system", lambda: "Darwin")
    for transport, expected in (("blue", True), ("blea", True), ("bltn", False), ("usb ", False)):
        monkeypatch.setattr(audio, "_property", lambda obj, sel, t=transport:
                            77 if sel == "dIn " else audio._four(t))
        assert audio.default_input_is_bluetooth() is expected, transport


def test_an_unreadable_device_is_never_called_bluetooth(monkeypatch):
    monkeypatch.setattr(audio.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(audio, "_property", lambda *_a: None)
    assert audio.default_input_is_bluetooth() is False


def test_other_systems_keep_todays_behaviour(monkeypatch):
    monkeypatch.setattr(audio.platform, "system", lambda: "Windows")
    assert audio.default_input_is_bluetooth() is False
    assert audio.recording_device() is None


def test_the_real_check_runs_without_raising_on_this_machine():
    assert audio.default_input_is_bluetooth() in (True, False)


# ── choosing the computer's own microphone ────────────────────

def test_the_built_in_microphone_is_chosen_over_the_bluetooth_default():
    assert audio.pick_built_in_input(DEVICES, default_index=2) == 0


def test_it_never_picks_the_default_or_an_output_only_device():
    only_speakers = [{"name": "MacBook Air Speakers", "max_input_channels": 0},
                     {"name": "HBTS003", "max_input_channels": 1}]
    assert audio.pick_built_in_input(only_speakers, default_index=1) is None


def test_no_built_in_microphone_means_no_choice():
    assert audio.pick_built_in_input([{"name": "HBTS003", "max_input_channels": 1}], 0) is None


def test_recording_uses_the_built_in_mic_only_when_the_default_is_bluetooth(monkeypatch):
    import sounddevice as sd

    from types import SimpleNamespace

    monkeypatch.setattr(sd, "query_devices", lambda: DEVICES)
    # Replace `sd.default` whole: patching `sd.default.device` "restores" a
    # live view of the setting, leaving device 2 as the default for every
    # later test (which then can't open a microphone).
    monkeypatch.setattr(sd, "default", SimpleNamespace(device=(2, 3)))
    monkeypatch.setattr(audio, "default_input_is_bluetooth", lambda: True)
    assert audio.recording_device() == 0
    monkeypatch.setattr(audio, "default_input_is_bluetooth", lambda: False)
    assert audio.recording_device() is None, "an ordinary default is left alone"


# ── "Hey Mike" waits instead of ruining the headset ───────────

class _Backend:
    started = 0

    def start(self):
        _Backend.started += 1
        return True


def test_the_wake_word_does_not_open_a_bluetooth_microphone(monkeypatch):
    from voice import wake, wake_word

    made = []
    monkeypatch.setattr(wake, "make_backend", lambda cb: made.append(1) or _Backend())
    monkeypatch.setattr(audio, "default_input_is_bluetooth", lambda: True)

    detector = wake_word.WakeWordDetector(on_wake=lambda: None)
    assert detector.start() is False
    assert detector.paused_for_bluetooth is True
    assert made == [], "nothing may be created, let alone listening"


def test_the_wake_word_starts_normally_when_the_microphone_is_not_bluetooth(monkeypatch):
    from voice import wake, wake_word

    monkeypatch.setattr(wake, "make_backend", lambda cb: _Backend())
    monkeypatch.setattr(audio, "default_input_is_bluetooth", lambda: False)

    detector = wake_word.WakeWordDetector(on_wake=lambda: None)
    assert detector.start() is True and detector.paused_for_bluetooth is False


def test_the_wake_word_starts_once_the_headset_is_no_longer_the_microphone(monkeypatch):
    """Switching the input back to the Mac's microphone must bring it back."""
    from voice import wake, wake_word

    monkeypatch.setattr(wake, "make_backend", lambda cb: _Backend())
    state = {"bt": True}
    monkeypatch.setattr(audio, "default_input_is_bluetooth", lambda: state["bt"])
    detector = wake_word.WakeWordDetector(on_wake=lambda: None)
    assert detector.start() is False
    state["bt"] = False
    assert detector.start() is True and detector.paused_for_bluetooth is False


class _StoppableBackend(_Backend):
    def __init__(self):
        self.running = False

    def start(self):
        self.running = True
        return True

    def stop(self):
        self.running = False


def _detector(monkeypatch, state):
    from voice import wake, wake_word

    backend = _StoppableBackend()
    monkeypatch.setattr(wake, "make_backend", lambda cb: backend)
    monkeypatch.setattr(audio, "default_input_is_bluetooth", lambda: state["bt"])
    return wake_word.WakeWordDetector(on_wake=lambda: None), backend


def test_a_headset_connected_while_mike_runs_pauses_the_wake_word(monkeypatch):
    """AirPods put in after Mike opened become the microphone; the listener
    follows the default, so it must let go of them."""
    state = {"bt": False}
    detector, backend = _detector(monkeypatch, state)
    assert detector.start() is True and backend.running

    state["bt"] = True
    detector.recheck()
    assert detector.paused_for_bluetooth is True and not backend.running

    detector.recheck()                       # still Bluetooth: stays paused
    assert not backend.running


def test_the_wake_word_comes_back_when_the_headset_goes(monkeypatch):
    state = {"bt": True}
    detector, backend = _detector(monkeypatch, state)
    assert detector.start() is False and not backend.running

    state["bt"] = False
    detector.recheck()
    assert detector.paused_for_bluetooth is False and backend.running


def test_recheck_never_starts_a_wake_word_the_user_switched_off(monkeypatch):
    state = {"bt": True}
    detector, backend = _detector(monkeypatch, state)
    detector.start()
    detector.stop()                          # Settings: "Hey Mike" off

    state["bt"] = False
    detector.recheck()
    assert not backend.running


def test_the_mac_listener_is_not_left_deaf_after_a_stop_mid_speech():
    """Stopped while Mike was speaking, then started again: it must hear."""
    import pytest

    macos = pytest.importorskip("voice.wake.macos")
    backend = macos.MacWakeWord(on_wake=lambda: None)
    backend._active, backend._suppressed = True, True
    backend.stop()
    assert backend._suppressed is False


# ── the recorder passes the choice to the audio system ────────

def test_the_recorder_records_from_the_chosen_device(monkeypatch):
    import sounddevice as sd

    from voice.recorder import PushToTalkRecorder

    seen = {}

    class _Stream:
        def __init__(self, **kwargs):
            seen.update(kwargs)

        def start(self):
            pass

        def stop(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(sd, "InputStream", _Stream)
    monkeypatch.setattr(audio, "recording_device", lambda: 0)
    recorder = PushToTalkRecorder()
    assert recorder.start() is True
    assert seen["device"] == 0


# ── the settings row says why ─────────────────────────────────

def test_settings_explains_why_hey_mike_is_paused(monkeypatch):
    from ui.workspace.pages import VoiceTab

    monkeypatch.setattr(audio, "default_input_is_bluetooth", lambda: True)
    text = VoiceTab._wake_description()
    assert "Bluetooth" in text and "F6" in text

    monkeypatch.setattr(audio, "default_input_is_bluetooth", lambda: False)
    assert "Bluetooth" not in VoiceTab._wake_description()
