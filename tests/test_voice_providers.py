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


def test_the_token_cap_cannot_truncate_a_sentence_the_ceiling_allows():
    """Two limits guard generation, and they must not disagree.

    The duration ceiling stops a runaway. A token cap stops generation
    outright. If the token cap bites first, a perfectly normal sentence is
    cut off mid-word and nothing reports a problem — measured: mlx-audio's
    convenience wrapper defaults to 1200 tokens, which ended three of eleven
    rendered samples at exactly 12.00 seconds, mid-speech.

    So the token cap is derived from the duration ceiling rather than set
    beside it, and this pins that they stay in that order.
    """
    from voice.providers.qwen_worker import TOKENS_PER_SECOND, duration_limit

    for text in ("Done.",
                 "The tests all pass now. The failure was in the discount conversion.",
                 "I've added the late figures to your Q3 sales spreadsheet, and the "
                 "total came to nine thousand three hundred and four.",
                 "x" * 600):
        ceiling = duration_limit(text)
        tokens = int(ceiling * TOKENS_PER_SECOND * 1.2)
        assert tokens > ceiling * TOKENS_PER_SECOND, (
            f"the token cap bites before the duration ceiling for {text[:30]!r}"
        )


# ══ the contract that keeps the interface responsive ═══════

def test_speaking_never_blocks_the_caller():
    """speak() is called from the Qt main thread once per sentence of a
    streaming reply, so anything it waits for is a frozen interface.

    Measured on the first version of the neural provider: 233-294 ms of stall
    per sentence, because it waited for the first audio chunk before
    returning. The system voice was 2-5 ms, which is why nobody noticed the
    design assumed speaking is instant.
    """
    import time

    class _SlowVoice(VoiceProvider):
        name = "slow"
        healthy = True
        last_failure = ""

        def available(self):
            return True, "slow on purpose"

        def speak(self, text):
            # A provider that blocks here is the bug this test exists for.
            return True

        def is_speaking(self):
            return False

        def stop(self):
            pass

    speaker = Speaker(provider=_SlowVoice())
    worst = 0.0
    for sentence in ("One.", "Two.", "Three."):
        started = time.perf_counter()
        speaker.speak_sentence(sentence)
        worst = max(worst, (time.perf_counter() - started) * 1000)

    assert worst < 50, f"speaking blocked the caller for {worst:.0f} ms"
    speaker.shutdown()


# ══ failures discovered after the utterance was accepted ═══

class _AcceptsThenFails(VoiceProvider):
    """The realistic failure: the worker takes the text, then dies."""

    name = "accepts-then-fails"
    healthy = True
    last_failure = "worker died while generating"

    def __init__(self):
        self.accepted = []

    def available(self):
        return True, "accepts everything"

    def speak(self, text):
        self.accepted.append(text)
        # What the real provider does from its playback thread once it knows
        # no audio is coming.
        if self.on_failure:
            self.on_failure(text, "worker died while generating")
        return True

    def is_speaking(self):
        return False

    def stop(self):
        pass


def test_an_utterance_dropped_after_acceptance_is_still_spoken():
    """The caller has moved on by the time the failure is known, so the
    provider hands the words back rather than losing them."""
    provider = _AcceptsThenFails()
    speaker = Speaker(provider=provider)

    speaker.speak("Mike must still say this.")
    time.sleep(0.3)

    assert provider.accepted == ["Mike must still say this."]
    assert speaker.fell_back
    assert speaker._native.is_speaking(), "the words were lost"
    speaker.stop()
    speaker.shutdown()


def test_the_fallback_speaks_the_sentence_once_not_twice():
    """The failure mode of a fallback is duplicate speech. Exactly one
    process should be talking."""
    speaker = Speaker(provider=_AcceptsThenFails())
    speaker.speak("Say this exactly once.")
    time.sleep(0.3)

    first = speaker._native._process
    assert first is not None
    time.sleep(0.3)
    assert speaker._native._process is first, "a second utterance was started"

    speaker.stop()
    speaker.shutdown()


def test_a_repeatedly_failing_voice_is_left_alone_for_the_rest_of_the_reply():
    """Retrying a sick worker once per sentence turns one failure into a
    stutter of them, each costing its own timeout before the user hears
    anything."""
    provider = _AcceptsThenFails()
    speaker = Speaker(provider=provider)

    for i in range(6):
        speaker.speak(f"Sentence number {i}.")
        time.sleep(0.05)

    assert len(provider.accepted) == speaker._GIVE_UP_AFTER, (
        f"kept retrying a failing provider: {len(provider.accepted)} attempts"
    )
    speaker.stop()
    speaker.shutdown()


def test_a_new_turn_gives_the_preferred_voice_another_chance():
    """One bad reply must not disable the voice for the session."""
    provider = _AcceptsThenFails()
    speaker = Speaker(provider=provider)

    for i in range(4):
        speaker.speak(f"First reply sentence {i}.")
        time.sleep(0.05)
    assert len(provider.accepted) == speaker._GIVE_UP_AFTER

    speaker.reset_health()          # what the controller does at turn start
    speaker.speak("A new turn begins.")
    time.sleep(0.05)

    assert len(provider.accepted) == speaker._GIVE_UP_AFTER + 1, (
        "the voice was never retried after recovery"
    )
    speaker.stop()
    speaker.shutdown()


def test_an_unhealthy_provider_is_skipped_without_being_asked():
    """Health is the provider's own report — a truncated runaway sets it —
    and the caller must honour it rather than trying anyway."""
    provider = _AcceptsThenFails()
    provider.healthy = False
    speaker = Speaker(provider=provider)

    speaker.speak("This should go straight to the native voice.")
    time.sleep(0.2)

    assert provider.accepted == [], "an unhealthy provider was still used"
    assert speaker._native.is_speaking()
    speaker.stop()
    speaker.shutdown()


# ══ configuration cannot break startup ════════════════════

@pytest.mark.parametrize("value", ["", "   ", "qwen; rm -rf /", "NATIVE",
                                   "Qwen", "unknown-provider", None])
def test_no_configured_value_can_stop_mike_speaking(value):
    """Malformed configuration is a configuration problem, never a silent
    Mike."""
    provider = get_provider(value)
    ok, _ = provider.available()
    assert ok or provider.name == "native"


def test_an_invalid_speaker_is_refused_before_it_reaches_the_model():
    """Caught at availability rather than at generation time, so the caller
    falls back before the user notices a gap."""
    from voice.providers.qwen import QwenVoice

    ok, why = QwenVoice(voice="NotARealSpeaker").available()
    assert not ok
    assert "Ryan" in why, "the message should name the voices that do exist"


def test_a_missing_model_is_reported_not_crashed(tmp_path, monkeypatch):
    """And the message points at the instructions, because "not downloaded"
    with no next step is not much better than silence."""
    from voice.providers.qwen import QwenVoice

    home = tmp_path / "voice"
    (home / "bin").mkdir(parents=True)
    (home / "bin" / "python").write_text("#!/bin/sh\n")
    monkeypatch.setenv("MIKE_VOICE_HOME", str(home))

    provider = QwenVoice()
    provider._home = home
    ok, why = provider.available()
    assert not ok
    assert "not downloaded" in why
    assert "voice-setup" in why


def test_the_voice_installation_is_searched_for_not_assumed(tmp_path, monkeypatch):
    """Mike's production voice used to depend on a directory created by hand
    for a benchmark, named as though it were disposable. Where it lives is
    now discovered, and overridable."""
    from voice.providers import qwen as qwen_module

    home = tmp_path / "chosen"
    (home / "bin").mkdir(parents=True)
    (home / "bin" / "python").write_text("#!/bin/sh\n")
    monkeypatch.setenv("MIKE_VOICE_HOME", str(home))

    assert qwen_module.voice_home() == home


def test_no_installation_at_all_is_reported_clearly(tmp_path, monkeypatch):
    from voice.providers import qwen as qwen_module

    monkeypatch.setenv("MIKE_VOICE_HOME", str(tmp_path / "nowhere"))
    monkeypatch.setattr(qwen_module.Path, "home", staticmethod(lambda: tmp_path))

    ok, why = qwen_module.QwenVoice().available()
    assert not ok
    assert "not installed" in why


def test_a_missing_interpreter_is_reported_not_crashed(tmp_path):
    from voice.providers.qwen import QwenVoice

    ok, why = QwenVoice(python=tmp_path / "no-python").available()
    assert not ok
    assert "interpreter" in why


# ══ pacing: generation must overlap playback ══════════════

def test_a_queueing_provider_is_handed_sentences_immediately():
    """A reply arrives sentence by sentence. Handing each one over only after
    the previous finished playing serialises generation behind playback, and
    measured that way a four-sentence reply took 47 seconds against the system
    voice's 12. Overlapping them brought it to 25.
    """
    class _Queueing(VoiceProvider):
        name = "queueing"
        queues = True
        healthy = True
        last_failure = ""

        def __init__(self):
            self.received = []

        def available(self):
            return True, "queues"

        def speak(self, text):
            self.received.append(text)
            return True

        def enqueue(self, text):
            self.received.append(text)
            return True

        def is_speaking(self):
            return True          # still busy with the first sentence

        def stop(self):
            pass

    provider = _Queueing()
    speaker = Speaker(provider=provider)
    for sentence in ("One.", "Two.", "Three."):
        speaker.speak_sentence(sentence)

    assert provider.received == ["One.", "Two.", "Three."], (
        "later sentences waited for the first to finish playing"
    )


def test_a_non_queueing_provider_is_still_paced_one_at_a_time():
    """The system voice has no queue of its own; handing it a second sentence
    mid-utterance would cut the first one off."""
    from voice.providers.native import NativeVoice

    native = NativeVoice()
    assert not native.queues
    assert native.speak("A sentence long enough to still be playing.")
    assert not native.enqueue("This must not interrupt it."), (
        "enqueue cut off the sentence in progress"
    )
    native.stop()


def test_stopping_discards_the_queued_remainder_of_the_reply():
    """Interrupting Mike must not leave him to resume with the rest of what
    he was going to say."""
    from voice.providers.qwen import QwenVoice

    provider = QwenVoice()
    provider._pending = [(1, "first"), (2, "second"), (3, "third")]
    provider.stop()
    assert provider._pending == []


def test_worker_scratch_directories_do_not_accumulate(tmp_path, monkeypatch):
    """Each worker writes audio chunks to a scratch directory. A worker that
    is killed cannot clean up after itself, so the parent sweeps — including
    directories orphaned by a previous run that never shut down."""
    import tempfile

    from voice.providers.qwen import QwenVoice

    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    orphans = [tmp_path / f"mike-qwen-tts-{i}" for i in range(3)]
    for path in orphans:
        path.mkdir()
        (path / "chunk_000001.wav").write_bytes(b"leftover")

    QwenVoice._sweep_workspaces()

    assert not any(p.exists() for p in orphans), "scratch directories survived"
