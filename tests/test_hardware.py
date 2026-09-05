"""What the machine is, and whether what Mike is running fits on it.

Mike's configuration states what to run — a 9B brain at a 40,960 token
context, a neural voice — and that is right for the machine it was tuned on
and a guess everywhere else. These pin the measurement layer that a future
answer would have to be built on.

Deliberately not tested here: any rule mapping machine size to model name.
No such rule exists, because it would be wrong the moment a new model appears
and could not account for what else the user has open.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401

from brain.hardware import Machine, current


def test_the_machine_is_detected_with_plausible_numbers():
    machine = current(refresh=True)

    assert machine.total_memory_gb > 0.5, "no total memory detected"
    assert machine.cpu_cores >= 1
    assert machine.free_disk_gb > 0
    assert machine.available_memory_gb <= machine.total_memory_gb
    assert machine.system in ("Darwin", "Linux", "Windows")


def test_apple_silicon_is_recognised_as_unified_memory():
    """The single most important fact for deciding what can be resident: a
    model on the GPU takes memory from everything else rather than using a
    separate card's."""
    import platform

    machine = current(refresh=True)
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        assert machine.unified_memory
        assert machine.metal
        assert any("unified" in note for note in machine.notes)


def test_headroom_reserves_room_for_the_rest_of_the_system():
    """Ignoring that reserve is how a 6.2 GB model plus a 0.9 GB voice drove
    free memory to 60 MB and made every reply stutter."""
    machine = current(refresh=True)

    generous = machine.headroom_gb(reserve_gb=0.0)
    careful = machine.headroom_gb(reserve_gb=4.0)

    assert generous >= careful
    assert careful >= 0.0, "headroom must never go negative"


def test_hosting_decisions_follow_from_headroom():
    machine = Machine(
        system="Darwin", architecture="arm64", chip="test", cpu_cores=8,
        total_memory_gb=16.0, available_memory_gb=10.0, swap_used_gb=0.0,
        free_disk_gb=100.0, unified_memory=True, metal=True,
    )
    assert machine.headroom_gb(reserve_gb=3.0) == 7.0
    assert machine.can_host(6.2)
    assert not machine.can_host(8.0)
    assert not machine.under_pressure()


def test_a_squeezed_machine_reports_pressure():
    machine = Machine(
        system="Darwin", architecture="arm64", chip="test", cpu_cores=8,
        total_memory_gb=16.0, available_memory_gb=0.9, swap_used_gb=5.0,
        free_disk_gb=10.0, unified_memory=True, metal=True,
    )
    assert machine.under_pressure()
    assert machine.headroom_gb() == 0.0
    assert not machine.can_host(0.5)


def test_pressure_is_re_read_rather_than_cached():
    """Static facts can be cached; how much memory is free right now cannot.
    A cached snapshot would have callers deciding what fits based on how the
    machine looked when Mike started."""
    first = current()
    second = current()

    assert first.total_memory_gb == second.total_memory_gb
    assert first.chip == second.chip
    # Re-read, not reused: the object is rebuilt each call.
    assert first is not second


def test_the_description_is_readable():
    text = current(refresh=True).describe()
    assert "memory:" in text and "disk:" in text
    assert len(text.splitlines()) >= 3


def test_detection_never_raises_on_this_platform():
    for _ in range(3):
        Machine.detect()


def test_diagnostics_reports_hardware_and_voice():
    from brain import diagnostics

    hardware = diagnostics.check_hardware()
    assert "total_memory_gb" in hardware
    assert isinstance(hardware["concerns"], list)

    voice = diagnostics.check_voice()
    assert voice["configured"] in ("native", "qwen")
    assert voice["will_use"] in ("native", "qwen")
    # The configured voice and the one that will speak are not always the
    # same, and when they differ the reason must be recorded.
    if voice["configured"] != voice["will_use"]:
        assert voice.get("reason")


# ── configuration cannot carry the wrong shape ────────────

def test_a_hand_edited_preference_of_the_wrong_type_is_ignored(tmp_path, monkeypatch):
    """The allowlist checked keys and not values, so a file could put a dict
    where a voice name belongs, or the word "fast" where a speaking rate
    belongs, and the wrong type travelled to the code that used it."""
    import importlib
    import json

    monkeypatch.setenv("MIKE_DATA_DIR", str(tmp_path))
    (tmp_path / "preferences.json").write_text(json.dumps({
        "voice_provider": {"nested": True},
        "voice_rate": "fast",
        "wake_word_enabled": "yes",
        "voice_qwen_speaker": "Aiden",      # this one is fine
    }))

    from config import preferences
    importlib.reload(preferences)

    assert preferences.get("voice_provider") == "native", "a dict got through"
    assert preferences.get("voice_rate") == 185, "a string rate got through"
    assert preferences.get("wake_word_enabled") is True, "a string bool got through"
    assert preferences.get("voice_qwen_speaker") == "Aiden", "a valid value was lost"


def test_setting_a_value_of_the_wrong_type_is_refused(tmp_path, monkeypatch):
    import importlib

    monkeypatch.setenv("MIKE_DATA_DIR", str(tmp_path))
    from config import preferences
    importlib.reload(preferences)

    preferences.set_value("voice_rate", "very fast")
    assert preferences.get("voice_rate") == 185

    preferences.set_value("voice_rate", 200)
    assert preferences.get("voice_rate") == 200


def test_a_boolean_is_not_accepted_where_a_number_belongs(tmp_path, monkeypatch):
    """True is an int in Python, so the obvious isinstance check accepts it."""
    import importlib

    monkeypatch.setenv("MIKE_DATA_DIR", str(tmp_path))
    from config import preferences
    importlib.reload(preferences)

    preferences.set_value("voice_rate", True)
    assert preferences.get("voice_rate") == 185


# ── what a model costs, beside what it can do ─────────────

def test_locality_is_derived_rather_than_declared():
    """A provider that reaches the network is not local however it is
    labelled, so this follows from the provider rather than a flag someone
    has to remember to set."""
    from brain.providers.base import Capabilities

    assert Capabilities(model="qwen3.5:9b", provider="ollama").is_local
    assert not Capabilities(model="gpt", provider="openai").is_local
    assert not Capabilities(model="deepseek", provider="deepseek").is_local


def test_an_unmeasured_cost_is_unknown_rather_than_no():
    """"We have not measured this" and "this does not fit" are different
    answers, and a caller that conflates them will refuse models it has
    simply never tried."""
    from brain.providers.base import Capabilities

    caps = Capabilities(model="qwen3.5:9b", provider="ollama")
    assert caps.fits_on(current()) is None


def test_a_measured_model_is_judged_against_real_headroom():
    from brain.hardware import Machine
    from brain.providers.base import Capabilities

    roomy = Machine(
        system="Darwin", architecture="arm64", chip="test", cpu_cores=8,
        total_memory_gb=32.0, available_memory_gb=20.0, swap_used_gb=0.0,
        free_disk_gb=100.0, unified_memory=True, metal=True,
    )
    cramped = Machine(
        system="Darwin", architecture="arm64", chip="test", cpu_cores=8,
        total_memory_gb=8.0, available_memory_gb=4.0, swap_used_gb=2.0,
        free_disk_gb=20.0, unified_memory=True, metal=True,
    )
    caps = Capabilities(model="qwen3.5:9b", provider="ollama") \
        .with_observation(observed_resident_gb=6.2)

    assert caps.fits_on(roomy) is True
    assert caps.fits_on(cramped) is False


def test_a_cloud_model_has_no_local_footprint_to_judge():
    from brain.providers.base import Capabilities

    caps = Capabilities(model="gpt", provider="openai") \
        .with_observation(observed_resident_gb=6.2)
    assert caps.fits_on(current()) is None, "a cloud model was judged on local memory"


def test_only_observations_can_be_set_from_a_run():
    """Declarations describe what a model claims and observations describe
    what it did. Letting a run overwrite a declaration erases the distinction
    the class exists for, and can() would have nothing left to prefer."""
    import pytest

    from brain.providers.base import Capabilities

    caps = Capabilities(model="m", provider="ollama")
    with pytest.raises(ValueError) as exc:
        caps.with_observation(declared_tools=False)
    assert "not observations" in str(exc.value)

    updated = caps.with_observation(observed_tools=True, observed_first_token_ms=620)
    assert updated.observed_tools is True
    assert updated.observed_first_token_ms == 620
    assert updated.declared_tools is caps.declared_tools
