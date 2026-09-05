"""The voice-provider boundary, and the guarantees a second voice must keep.

Mike had one voice and it was the operating system's. Adding a neural one
introduces failure modes the old path did not have: a worker that will not
start, a model that produces nothing, and — measured, once in twenty-eight
generations — a run that produced ninety-six seconds of audio for a
seven-second sentence.

None of that may reach the user. The rule these tests pin is that Mike always
speaks: if the configured voice cannot, the native one finishes the sentence,
and Mike is never silent because the better voice broke.
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401

import pytest

from voice.providers import get_provider
from voice.providers.base import VoiceProvider
from voice.providers.native import NativeVoice
from voice.speaker import Speaker


# ── the boundary ──────────────────────────────────────────

def test_the_native_voice_is_always_available():
    """It is the fallback, so it has to be the thing that cannot fail."""
    ok, why = NativeVoice().available()
    assert ok, why


def test_an_unknown_provider_falls_back_rather_than_raising():
    """A bad configuration value must not stop Mike from speaking."""
    assert get_provider("does-not-exist").name == "native"
    assert get_provider(None).name == "native"
    assert get_provider("").name == "native"


def test_both_providers_satisfy_the_interface():
    from voice.providers.qwen import QwenVoice

    for provider in (NativeVoice(), QwenVoice()):
        assert isinstance(provider, VoiceProvider)
        for method in ("available", "speak", "is_speaking", "stop", "shutdown"):
            assert callable(getattr(provider, method)), f"{provider.name}.{method}"


def test_stop_is_safe_when_nothing_is_speaking():
    for provider in (NativeVoice(), get_provider("does-not-exist")):
        for _ in range(3):
            provider.stop()
        assert not provider.is_speaking()


# ── the fallback rule ─────────────────────────────────────

class _BrokenVoice(VoiceProvider):
    """A provider that behaves exactly as a dead Qwen worker would."""

    name = "broken"
    last_failure = "deliberately broken for this test"

    def __init__(self):
        self.attempts = 0

    def available(self):
        return True, "pretends to work"

    def speak(self, text):
        self.attempts += 1
        return False

    def is_speaking(self):
        return False

    def stop(self):
        pass


def test_a_failing_provider_falls_back_and_mike_still_speaks():
    """The central guarantee. The utterance is not lost, it changes voice."""
    broken = _BrokenVoice()
    speaker = Speaker(provider=broken)

    speaker.speak("Mike must still say this out loud.")
    time.sleep(0.3)

    assert broken.attempts == 1, "the configured provider was never tried"
    assert speaker.fell_back, "the fallback was not recorded"
    assert speaker.is_speaking(), "Mike went silent instead of falling back"
    assert speaker._native.is_speaking(), "the native voice did not pick it up"

    speaker.stop()
    assert not speaker.is_speaking()
    speaker.shutdown()


def test_stopping_after_a_fallback_stops_the_voice_that_is_actually_talking():
    """After a fallback the noise is coming from the native voice while the
    configured provider is something else. Stopping only the configured one
    would leave Mike talking over the user."""
    speaker = Speaker(provider=_BrokenVoice())
    speaker.speak("A sentence long enough that stopping it matters.")
    time.sleep(0.3)
    assert speaker.is_speaking()

    speaker.stop()

    assert not speaker.is_speaking()
    assert speaker._native._process is None
    speaker.shutdown()


def test_a_failing_provider_does_not_stop_the_runtime():
    """Voice is an output device. Losing it must not lose Mike."""
    from brain.core_runtime import CoreRuntime

    speaker = Speaker(provider=_BrokenVoice())
    speaker.speak("this will fall back")
    speaker.stop()

    result = CoreRuntime()._execute_tool("calculate", {"expression": "2 + 2"})
    assert result["status"] == "success"
    speaker.shutdown()


# ── the runaway guard ─────────────────────────────────────

def test_the_duration_ceiling_allows_normal_speech():
    """Measured: the same sentence came out anywhere from 6.2 s to 10.0 s.
    A ceiling that clipped normal variance would be worse than no ceiling,
    because it would break every long reply instead of a rare bad one."""
    from voice.providers.qwen_worker import duration_limit

    sentence = ("I've added the late figures to your Q3 sales spreadsheet, and "
                "the total came to nine thousand three hundred and four.")
    limit = duration_limit(sentence)

    assert limit > 10.0, f"the ceiling would clip the slowest normal run: {limit}"
    assert limit < 25.0, f"the ceiling is too loose to catch a runaway: {limit}"


def test_the_duration_ceiling_catches_the_measured_runaway():
    """The real failure: 96 seconds of audio for a seven-second line."""
    from voice.providers.qwen_worker import duration_limit

    sentence = ("I've added the late figures to your Q3 sales spreadsheet, and "
                "the total came to nine thousand three hundred and four.")
    assert duration_limit(sentence) < 96.0, "the runaway would have reached the user"


def test_short_text_is_not_clipped_by_a_proportional_ceiling():
    """A proportional limit alone would give "Done." a fraction of a second,
    which is shorter than the word takes to say."""
    from voice.providers.qwen_worker import duration_limit

    assert duration_limit("Done.") >= 4.0
    assert duration_limit("Yes.") >= 4.0


@pytest.mark.parametrize("length,ceiling", [(20, 4.0), (100, 15.3), (400, 61.0)])
def test_the_ceiling_scales_with_the_text(length, ceiling):
    from voice.providers.qwen_worker import duration_limit

    assert duration_limit("x" * length) == pytest.approx(ceiling, abs=1.0)


# ── configuration ─────────────────────────────────────────

def test_the_default_voice_is_the_native_one():
    """Until the real conversation test says otherwise, Samantha ships."""
    from config import preferences

    assert str(preferences.get("voice_provider", "native")).lower() == "native"
    assert Speaker().provider_name == "native"


def test_one_voice_is_one_object():
    """With native configured, Speaker held two NativeVoice instances. Stop
    still worked because it stopped both, but "which one is speaking?" had
    two answers, and that is the kind of ambiguity that hides a bug later."""
    speaker = Speaker()
    assert speaker._provider is speaker._native
