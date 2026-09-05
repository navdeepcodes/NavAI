"""The Qwen worker driven for real: interruption, crashes, shutdown.

Marked drives_real_apps because it starts a subprocess, loads a 0.9 GB model
and produces audio. The stubbed equivalents in test_voice_providers.py cover
the logic; these cover the parts only a real worker can be wrong about —
whether a killed process is noticed, whether audio actually stops, and
whether anything is left running afterwards.

    MIKE_RUN_APP_E2E=1 venv/bin/python -m pytest tests/test_voice_worker_e2e.py -q
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401

import pytest

pytestmark = pytest.mark.drives_real_apps


def _qwen():
    from voice.providers.qwen import QwenVoice

    provider = QwenVoice()
    ok, why = provider.available()
    if not ok:
        pytest.skip(f"Qwen voice unavailable: {why}")
    provider.warm_up()
    return provider


def _audio_processes() -> int:
    """Audio players started by *this* process, not by the whole machine.

    The first version counted every afplay running anywhere, which made these
    tests fail whenever another test in the suite happened to be speaking at
    the same moment — and would have failed just as readily if someone were
    playing music. A test that depends on the rest of the computer being
    silent is a test that reports contention as a bug.
    """
    mine = subprocess.run(["pgrep", "-P", str(os.getpid())],
                          capture_output=True, text=True).stdout.split()
    count = 0
    for pid in mine:
        comm = subprocess.run(["ps", "-p", pid, "-o", "comm="],
                              capture_output=True, text=True).stdout.strip()
        if comm.endswith("afplay"):
            count += 1
    return count


LONG = ("I have finished going through all six regional spreadsheets, and each "
        "one now has a total row at the bottom with the revenue for that region.")


# ── barge-in at every point it can happen ─────────────────

@pytest.mark.parametrize("wait_ms", [0, 250, 900, 2000, 4000])
def test_interruption_stops_audio_whenever_it_arrives(wait_ms):
    """A person interrupts whenever they feel like it — before audio starts,
    mid-word, between chunks, deep into a long reply. All of them must
    silence Mike and leave him usable."""
    provider = _qwen()
    try:
        provider.speak(LONG)
        time.sleep(wait_ms / 1000)

        started = time.perf_counter()
        provider.stop()
        elapsed = (time.perf_counter() - started) * 1000

        assert elapsed < 250, f"stopping took {elapsed:.0f} ms"
        assert not provider.is_speaking(), "still reports speaking after stop"

        time.sleep(0.4)
        assert _audio_processes() == 0, "audio kept playing after the stop"
    finally:
        provider.shutdown()


def test_mike_is_usable_immediately_after_an_interruption():
    """The point of barge-in is the next thing the user says."""
    provider = _qwen()
    try:
        provider.speak(LONG)
        time.sleep(0.6)
        provider.stop()

        assert provider.speak("Yes, what would you like instead?")
        time.sleep(0.5)
        assert provider.is_speaking(), "the next utterance never started"
    finally:
        provider.stop()
        provider.shutdown()


def test_repeated_interruption_leaves_nothing_behind():
    """Ten interruptions in a row is a person changing their mind, not an
    edge case. Nothing may accumulate."""
    provider = _qwen()
    try:
        for _ in range(10):
            provider.speak(LONG)
            time.sleep(0.35)
            provider.stop()
        time.sleep(0.5)
        assert _audio_processes() == 0
        assert not provider.is_speaking()
        # One worker, still the same one — not a pile of them.
        assert provider._proc is not None and provider._proc.poll() is None
    finally:
        provider.shutdown()


def test_a_new_utterance_replaces_the_one_in_progress():
    """Speaking again while speaking must not produce two voices at once."""
    provider = _qwen()
    try:
        provider.speak(LONG)
        time.sleep(0.8)
        provider.speak("A different sentence entirely.")
        time.sleep(0.6)
        assert _audio_processes() <= 1, "two utterances were audible at once"
    finally:
        provider.stop()
        provider.shutdown()


# ── the worker as an unreliable external process ──────────

def test_a_killed_worker_is_noticed_and_the_words_are_not_lost():
    """The worker is a separate process and can die at any moment. When it
    does, the sentence the user is waiting for must still be spoken."""
    provider = _qwen()
    recovered = []
    provider.on_failure = lambda text, why: recovered.append((text, why))
    try:
        provider._proc.kill()
        provider._proc.wait(timeout=3)

        provider.speak("This sentence must survive the worker dying.")
        time.sleep(3.0)

        # Either the provider restarted the worker and spoke it, or it handed
        # the words back. Both are acceptable; losing them is not.
        assert recovered or provider.is_speaking() or provider._ready, (
            "the utterance was lost when the worker died"
        )
    finally:
        provider.shutdown()


def test_the_worker_restarts_after_being_killed():
    provider = _qwen()
    try:
        first_pid = provider._proc.pid
        provider._proc.kill()
        provider._proc.wait(timeout=3)

        assert provider._ensure_worker(), "the worker did not come back"
        assert provider._proc.pid != first_pid
        assert provider._proc.poll() is None
    finally:
        provider.shutdown()


def test_shutdown_during_generation_leaves_nothing_running():
    provider = _qwen()
    pid = provider._proc.pid
    provider.speak(LONG)
    time.sleep(0.2)          # mid-generation, before audio
    provider.shutdown()

    time.sleep(0.5)
    assert _audio_processes() == 0
    assert subprocess.run(["ps", "-p", str(pid)], capture_output=True).returncode != 0, \
        "the worker process outlived shutdown"


def test_shutdown_during_playback_leaves_nothing_running():
    provider = _qwen()
    pid = provider._proc.pid
    provider.speak(LONG)
    time.sleep(1.2)          # audible
    assert provider.is_speaking()
    provider.shutdown()

    time.sleep(0.5)
    assert _audio_processes() == 0
    assert subprocess.run(["ps", "-p", str(pid)], capture_output=True).returncode != 0


def test_shutdown_is_safe_to_repeat():
    provider = _qwen()
    for _ in range(3):
        provider.shutdown()


# ── runaway generation, triggered deliberately ────────────

def test_a_runaway_generation_is_cut_off_and_marks_the_voice_unwell():
    """The measured failure: 96 seconds of audio for a seven-second line.

    Reproduced by lowering the ceiling rather than by hoping the rare case
    turns up — the guard is what is under test, not the model's luck.
    """
    provider = QwenVoiceWithTinyCeiling()
    ok, why = provider.available()
    if not ok:
        pytest.skip(why)
    try:
        provider.warm_up()
        provider.speak(LONG)
        deadline = time.time() + 30
        while time.time() < deadline and not provider.last_truncation:
            time.sleep(0.2)

        assert provider.last_truncation, "the ceiling never fired"
        assert not provider.healthy, "a runaway must mark the voice unwell"
    finally:
        os.environ.pop("MIKE_QWEN_TTS_MAX_SECONDS", None)
        provider.shutdown()


def QwenVoiceWithTinyCeiling():
    """A provider whose worker will cut everything short, so the guard runs.

    The ceiling is lowered through the same configuration a person would
    use, which means this test exercises the real knob rather than a test-only
    back door — if the environment variable stopped being read, this fails.
    """
    from voice.providers.qwen import QwenVoice

    os.environ["MIKE_QWEN_TTS_MAX_SECONDS"] = "1.0"
    return QwenVoice()
