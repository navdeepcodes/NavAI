"""hostplatform.desktop: the hotkey backend contract and reduced_motion.

Real registration end-to-end on whichever platform provides a backend;
`HotkeyUnavailable` (not a silent no-op, not a fabricated success) on one
that doesn't yet. This is the property Phase 17 of the Windows-transition
audit calls a hard requirement: an unimplemented capability reports itself
as unimplemented rather than pretending to work.
"""
from __future__ import annotations

import os
import platform
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401

import pytest

from hostplatform import desktop


def test_reduced_motion_never_raises_and_returns_a_bool():
    result = desktop.reduced_motion()
    assert isinstance(result, bool)


@pytest.mark.skipif(platform.system() != "Darwin", reason="Darwin-only backend")
def test_darwin_hotkey_registers_for_real_and_reports_itself_honestly():
    calls = []
    backend = desktop.make_hotkey(lambda: calls.append(1))

    assert not backend.is_registered()
    assert backend.register() is True
    assert backend.is_registered() is True
    assert "Space" in backend.describe()

    backend.unregister()
    assert not backend.is_registered()


@pytest.mark.skipif(platform.system() != "Darwin", reason="Darwin-only backend")
def test_darwin_hotkey_register_is_idempotent():
    backend = desktop.make_hotkey(lambda: None)
    try:
        assert backend.register() is True
        assert backend.register() is True, "registering twice must not fail"
    finally:
        backend.unregister()


def test_an_unsupported_platform_raises_rather_than_faking_success(monkeypatch):
    """The honesty contract, verified directly: a platform with no backend
    must raise HotkeyUnavailable, never return a backend that silently does
    nothing."""
    monkeypatch.setattr(desktop.platform, "system", lambda: "Plan9")
    with pytest.raises(desktop.HotkeyUnavailable):
        desktop.make_hotkey(lambda: None)


if __name__ == "__main__":
    test_reduced_motion_never_raises_and_returns_a_bool()
    if platform.system() == "Darwin":
        test_darwin_hotkey_registers_for_real_and_reports_itself_honestly()
        test_darwin_hotkey_register_is_idempotent()
    print("\nAll hostplatform.desktop tests passed.")
