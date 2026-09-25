"""Speech-to-text holds its memory only while voice is in use.

Measured: loading small.en at startup committed 2.2GB for everyone, all the
time; next to the 11GB chat model it pushed a 16GB laptop to its commit limit
and every reply slowed with paging.
"""
import time

import pytest

import voice.recognizer.windows as rw


class _FakeModel:
    loads = 0

    def __init__(self, *a, **k):
        _FakeModel.loads += 1

    def transcribe(self, *a, **k):
        return iter(()), None


@pytest.fixture
def recognizer(monkeypatch):
    import faster_whisper
    import faster_whisper.utils

    _FakeModel.loads = 0
    downloads = []
    monkeypatch.setattr(faster_whisper, "WhisperModel", _FakeModel)
    monkeypatch.setattr(faster_whisper.utils, "download_model",
                        lambda size, **k: downloads.append(size) or "path")
    r = rw.WhisperRecognizer()
    r.downloads = downloads
    yield r
    if r._idle_timer:
        r._idle_timer.cancel()


def test_startup_downloads_but_does_not_load(recognizer):
    recognizer.prewarm()
    assert recognizer.downloads == ["small.en"]
    assert recognizer._model is None and _FakeModel.loads == 0


def test_listening_starts_the_load_and_idle_releases_it(recognizer, monkeypatch):
    monkeypatch.setattr(rw, "IDLE_UNLOAD_SECONDS", 0.3)
    recognizer.warm()
    deadline = time.time() + 3
    while recognizer._model is None and time.time() < deadline:
        time.sleep(0.02)
    assert recognizer._model is not None
    time.sleep(0.8)
    assert recognizer._model is None, "released after going idle"


def test_transcribing_after_release_loads_again(recognizer):
    recognizer.unload()
    done = []
    recognizer.transcribe_async("x.wav", done.append, done.append)
    deadline = time.time() + 3
    while not done and time.time() < deadline:
        time.sleep(0.02)
    assert done == [""] and _FakeModel.loads == 1
