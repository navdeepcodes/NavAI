"""From "Hey Mike" to text: the hand-over and the wait.

Measured with Mike's real wake word, recorder and Whisper on synthetic speech
fed in real time:

  - "Hey Mike, open Notepad and write a shopping list", one breath: nothing.
    The command was spoken before the recorder opened, and its first 0.3s --
    the person still talking -- was taken as the room's noise, so speech never
    crossed the threshold and the recording never ended.
  - On Windows the wake handler ran on the listener's own thread, and its
    QTimer.singleShot never fired there: the corner said "listening" and the
    mic never opened.
  - Every command waited ~1s for the silence to confirm, then ~2s for Whisper.

After: the command arrives in one breath, the recording starts on the UI
thread, and the words are transcribed during the pause that may end them.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import _isolate  # noqa: F401,E402

from voice import recorder as rec_mod  # noqa: E402

SPEECH, ROOM = 0.08, 0.003


# ── the recorder ─────────────────────────────────────────────────────────

class _Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def monotonic(self) -> float:
        return self.t


@pytest.fixture
def recorder(monkeypatch):
    class _NoStream:
        def __init__(self, *a, **k): pass
        def start(self): pass
        def stop(self): pass
        def close(self): pass
    monkeypatch.setattr(rec_mod.sd, "InputStream", _NoStream)
    clock = _Clock()
    monkeypatch.setattr(rec_mod, "time", SimpleNamespace(monotonic=clock.monotonic))
    r = rec_mod.PushToTalkRecorder()
    r.clock = clock
    return r


def _blocks(level: float, seconds: float) -> np.ndarray:
    rng = np.random.default_rng(7)
    return rng.normal(0, level, int(seconds * rec_mod.SAMPLE_RATE)).astype(np.float32)


def _feed(r, level: float, seconds: float) -> None:
    audio = _blocks(level, seconds)
    for i in range(0, len(audio), rec_mod.BLOCK_SIZE):
        r.clock.t += rec_mod.BLOCK_SECONDS
        r._audio_callback(audio[i:i + rec_mod.BLOCK_SIZE].reshape(-1, 1), rec_mod.BLOCK_SIZE, None, None)


def test_a_command_in_the_same_breath_as_the_name_is_speech_in_progress(recorder):
    assert recorder.start(preroll=_blocks(SPEECH, 1.0), noise_floor=ROOM)
    assert recorder.heard_speech, "still talking when the mic opened"
    _feed(recorder, SPEECH, 0.5)
    _feed(recorder, ROOM, 1.5)
    assert recorder.should_auto_stop, "and the end of the command ends the recording"
    recorder.stop()


def test_a_pause_after_the_name_waits_for_the_command(recorder):
    preroll = np.concatenate([_blocks(SPEECH, 0.4), _blocks(ROOM, 0.6)])
    recorder.start(preroll=preroll, noise_floor=ROOM)
    assert not recorder.heard_speech
    _feed(recorder, ROOM, 1.5)
    assert not recorder.should_auto_stop, "'Hey Mike.' and a breath is not the end"
    _feed(recorder, SPEECH, 1.0)
    _feed(recorder, ROOM, 1.5)
    assert recorder.should_auto_stop
    recorder.stop()


def test_a_threshold_measured_on_speech_comes_down_to_the_room(recorder):
    recorder.start()
    _feed(recorder, SPEECH, 0.3)                   # calibrated while talking
    assert recorder._speech_threshold > SPEECH
    _feed(recorder, ROOM, 1.0)
    assert recorder._speech_threshold < 3 * ROOM
    _feed(recorder, SPEECH, 1.0)
    assert recorder.heard_speech, "speech is above a threshold it can reach"
    _feed(recorder, ROOM, 1.5)
    assert recorder.should_auto_stop
    recorder.stop()


def test_nobody_speaking_closes_the_mic_after_a_few_seconds(recorder):
    recorder.start(noise_floor=ROOM)
    _feed(recorder, ROOM, rec_mod.NO_SPEECH_SECONDS - 0.5)
    assert not recorder.should_auto_stop
    _feed(recorder, ROOM, 1.0)
    assert recorder.should_auto_stop and not recorder.heard_speech
    recorder.stop()


# ── the wake listener's hand-over ────────────────────────────────────────

def test_the_wake_word_hands_over_what_was_said_after_the_name():
    from voice.wake.windows import WindowsWakeWord
    w = WindowsWakeWord(on_wake=lambda: None)
    w._active = True
    w._preroll = np.ones(1600, np.float32)          # after "Mike", at detection
    w._preroll_at = time.monotonic()
    w._preroll_floor = 0.004
    w._buf.extend(np.full(800, 0.5, np.float32))    # said while the recorder opened
    w.suppress()
    audio, floor = w.take_preroll()
    assert len(audio) == 2400 and floor == 0.004
    assert w.take_preroll() == (None, None), "once"


def test_a_stale_hand_over_is_not_used():
    from voice.wake.windows import WindowsWakeWord
    w = WindowsWakeWord(on_wake=lambda: None)
    w._preroll, w._preroll_at = np.ones(1600, np.float32), time.monotonic() - 6
    assert w.take_preroll() == (None, None)


def test_hey_mike_heard_on_the_listeners_thread_starts_recording_on_the_ui_thread(monkeypatch):
    from PySide6.QtCore import QThread
    from PySide6.QtWidgets import QApplication

    from brain.core_runtime import CoreRuntime
    from ui.controller.ui_controller import UIController
    from ui.panel.mike_panel import MikePanel

    app = QApplication.instance() or QApplication(sys.argv)
    ctrl = UIController(CoreRuntime(), MikePanel({}))
    started = []
    monkeypatch.setattr(ctrl, "_start_voice", lambda from_wake=False: started.append(
        (from_wake, QThread.currentThread() is app.thread())))

    listener = threading.Thread(target=ctrl._wake._on_wake)     # as the wake listener calls it
    listener.start()
    listener.join()
    deadline = time.monotonic() + 2
    while not started and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert started == [(True, True)], "recording starts, on the UI thread, with the preroll"


# ── a conversation, not a series of commands ─────────────────────────────

def _follow_up(monkeypatch, *, by_voice=True, state="idle", pref=True):
    from PySide6.QtWidgets import QApplication

    from brain.core_runtime import CoreRuntime
    from config import preferences
    from ui.controller.ui_controller import UIController
    from ui.panel.mike_panel import MikePanel

    app = QApplication.instance() or QApplication(sys.argv)
    ctrl = UIController(CoreRuntime(), MikePanel({}))
    listened = []
    monkeypatch.setattr(ctrl, "_start_voice",
                        lambda from_wake=False, follow_up=False: listened.append(follow_up))
    monkeypatch.setattr(ctrl._page, "state", lambda: state)
    monkeypatch.setattr(preferences, "get",
                        lambda key, default=None: pref if key == "voice_follow_up" else default)
    ctrl._by_voice = by_voice
    ctrl._maybe_follow_up()
    deadline = time.monotonic() + 0.6
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    return listened


def test_after_a_spoken_answer_mike_listens_for_a_reply(monkeypatch):
    assert _follow_up(monkeypatch) == [True]


def test_a_typed_turn_never_opens_the_mic(monkeypatch):
    assert _follow_up(monkeypatch, by_voice=False) == []


def test_no_listening_while_an_approval_is_waiting(monkeypatch):
    assert _follow_up(monkeypatch, state="needs_user") == [], "a spoken yes would start a new turn"


def test_the_student_can_turn_it_off(monkeypatch):
    assert _follow_up(monkeypatch, pref=False) == []


# ── transcribing during the pause ────────────────────────────────────────

class _Recorder:
    def __init__(self) -> None:
        self.heard_speech, self.silence_seconds, self.speech_epoch = False, 0.0, 0
        self.should_auto_stop = False

    def start(self, preroll=None, noise_floor=None, no_speech_seconds=None):
        return True

    def snapshot(self, path):
        return "early.wav"

    def stop(self):
        return "full.wav"


class _Recognizer:
    def __init__(self) -> None:
        self.calls = []

    def warm(self):
        pass

    def transcribe_async(self, path, on_done, on_error):
        self.calls.append((path, on_done))


@pytest.fixture
def voice(monkeypatch):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    import voice.recognizer as recognizer
    from voice.voice_input import VoiceInputManager
    stt = _Recognizer()
    monkeypatch.setattr(recognizer, "get_recognizer", lambda: stt)
    mgr = VoiceInputManager()
    mgr._recorder = _Recorder()
    got = {"text": [], "errors": [], "nothing": 0}
    mgr.transcription_ready.connect(got["text"].append)
    mgr.error.connect(got["errors"].append)
    mgr.nothing_heard.connect(lambda: got.__setitem__("nothing", got["nothing"] + 1))
    mgr.start_recording()
    return SimpleNamespace(mgr=mgr, rec=mgr._recorder, stt=stt, got=got, app=app)


def _settle(app):
    for _ in range(20):
        app.processEvents()
        time.sleep(0.005)


def test_the_words_are_transcribed_during_the_pause_that_ends_them(voice):
    voice.rec.heard_speech, voice.rec.speech_epoch, voice.rec.silence_seconds = True, 5, 0.4
    voice.mgr._check_auto_stop()
    assert [p for p, _ in voice.stt.calls] == ["early.wav"], "started in the pause"
    voice.rec.should_auto_stop = True                # the pause was the end
    voice.mgr._check_auto_stop()
    voice.stt.calls[0][1]("Open Notepad.")           # whisper finishes
    _settle(voice.app)
    assert voice.got["text"] == ["Open Notepad."]
    assert len(voice.stt.calls) == 1, "not transcribed twice"


def test_going_on_talking_discards_the_early_transcription(voice):
    voice.rec.heard_speech, voice.rec.speech_epoch, voice.rec.silence_seconds = True, 5, 0.4
    voice.mgr._check_auto_stop()
    voice.stt.calls[0][1]("Open")                    # the early one, of half the command
    voice.rec.speech_epoch, voice.rec.silence_seconds = 9, 0.0     # ...and they went on
    voice.mgr._check_auto_stop()
    voice.rec.should_auto_stop = True
    voice.mgr._check_auto_stop()
    assert [p for p, _ in voice.stt.calls][-1] == "full.wav"
    voice.stt.calls[-1][1]("Open Notepad and write a list.")
    _settle(voice.app)
    assert voice.got["text"] == ["Open Notepad and write a list."]


def test_a_mic_closed_with_nothing_said_is_not_an_error(voice):
    voice.rec.should_auto_stop = True
    voice.mgr._check_auto_stop()
    _settle(voice.app)
    assert voice.got["nothing"] == 1 and voice.got["errors"] == [] and voice.stt.calls == []


# ── Fast mode's speech-to-text ───────────────────────────────────────────

@pytest.fixture
def cloud(monkeypatch):
    from brain.providers import workers_ai_provider as fast
    from voice.recognizer.cloud import CloudRecognizer
    monkeypatch.setattr(fast, "_allowance_gone_until", 0.0)
    local = _Recognizer()
    local.warmed = False
    local.warm = lambda: setattr(local, "warmed", True)
    local.available = lambda: (True, "local")
    return SimpleNamespace(fast=fast, local=local, stt=CloudRecognizer(local))


def _run(stt, path="x.wav"):
    got = []
    stt.transcribe_async(path, on_done=got.append, on_error=got.append)
    deadline = time.monotonic() + 2
    while not got and time.monotonic() < deadline:
        time.sleep(0.01)
    return got


def test_fast_mode_off_means_local_whisper(cloud, monkeypatch):
    monkeypatch.setattr(cloud.fast, "fast_mode_on", lambda: False)
    cloud.stt.transcribe_async("x.wav", on_done=lambda t: None, on_error=lambda e: None)
    cloud.stt.warm()
    assert [p for p, _ in cloud.local.calls] == ["x.wav"] and cloud.local.warmed


def test_fast_mode_transcribes_on_cloudflare_and_leaves_the_local_model_unloaded(cloud, monkeypatch):
    monkeypatch.setattr(cloud.fast, "fast_mode_on", lambda: True)
    monkeypatch.setattr(type(cloud.stt), "_transcribe", staticmethod(lambda path: "What time is it?"))
    cloud.stt.warm()
    assert _run(cloud.stt) == ["What time is it?"]
    assert cloud.local.calls == [] and not cloud.local.warmed


def test_a_used_up_allowance_goes_local_for_chat_and_speech_alike(cloud, monkeypatch):
    monkeypatch.setattr(cloud.fast, "fast_mode_on", lambda: True)

    def used_up(path):
        raise RuntimeError('429 {"errors":[{"message":"you have used up your daily free '
                           'allocation of 10,000 neurons","code":4006}]}')
    monkeypatch.setattr(type(cloud.stt), "_transcribe", staticmethod(used_up))
    cloud.stt.transcribe_async("x.wav", on_done=lambda t: None, on_error=lambda e: None)
    deadline = time.monotonic() + 2
    while not cloud.local.calls and time.monotonic() < deadline:
        time.sleep(0.01)
    assert [p for p, _ in cloud.local.calls] == ["x.wav"], "the same audio, locally"
    assert not cloud.fast.allowance_left(), "and the chat model knows too"
