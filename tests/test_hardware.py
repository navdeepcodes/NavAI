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
