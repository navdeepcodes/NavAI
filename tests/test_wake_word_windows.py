"""The Windows wake word, end to end through its real pipeline: energy gate,
voice-activity check, tiny Whisper, name match -- with recorded audio fed in
at real-time pace where the microphone would be.

Two things must hold together: a spoken "Hey Mike" still wakes Mike, and
sound that isn't speech never reaches Whisper (measured before the VAD step:
typing/hum in the room kept Whisper running at up to 55% of a core).
"""
import platform
import threading
import time
import wave
from pathlib import Path

import numpy as np
import pytest

pytestmark = pytest.mark.skipif(platform.system() != "Windows", reason="Windows backend")

FIXTURES = Path(__file__).parent / "fixtures"
RATE = 16000


def _load(name):
    with wave.open(str(FIXTURES / name)) as w:
        rate = w.getframerate()
        audio = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    if rate != RATE:
        t = np.arange(int(len(audio) * RATE / rate)) / RATE
        audio = np.interp(t, np.arange(len(audio)) / rate, audio).astype(np.float32)
    return audio


def _run(detector_audio):
    from voice.wake import windows as W

    fired, transcribed = [], []
    det = W.WindowsWakeWord(on_wake=lambda: fired.append(time.monotonic()))
    det._open_stream = lambda: None                     # the feeder is the microphone
    model = det._load_model()
    real = model.transcribe
    model.transcribe = lambda *a, **k: (transcribed.append(1), real(*a, **k))[1]
    det.start()

    def feed():
        for i in range(0, len(detector_audio), 1600):   # 100ms blocks, like the stream
            det._on_audio(detector_audio[i:i + 1600].reshape(-1, 1), 1600, None, None)
            time.sleep(0.1)

    feeder = threading.Thread(target=feed)
    feeder.start()
    feeder.join()
    time.sleep(1.5)
    det.stop()
    return fired, transcribed


def _room(seconds, level=0.003, seed=0):
    return (level * np.random.default_rng(seed).standard_normal(int(seconds * RATE))).astype(np.float32)


def test_hey_mike_wakes_mike():
    wake = _load("voice_wake.wav") * 0.8
    fired, _ = _run(np.concatenate([_room(2.0), wake, _room(2.5, seed=1)]))
    assert fired, "a clear 'Hey Mike' must wake Mike"


def test_loud_sound_that_is_not_speech_never_reaches_whisper():
    t = np.arange(int(4 * RATE)) / RATE
    hum_and_clicks = (0.15 * np.sin(2 * np.pi * 120 * t)).astype(np.float32)
    hum_and_clicks[::1600] += 0.9
    fired, transcribed = _run(np.concatenate([_room(2.0), hum_and_clicks, _room(1.0, seed=2)]))
    assert not fired
    assert not transcribed, "non-speech sound must be rejected before Whisper runs"
