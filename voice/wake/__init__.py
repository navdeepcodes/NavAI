"""The wake-word backend for this machine."""
from __future__ import annotations

import platform
from typing import Callable

from voice.wake.base import WakeWordBackend


class WakeWordUnavailable(Exception):
    """No wake-word backend exists for this platform yet."""


def make_backend(on_wake: Callable[[], None]) -> WakeWordBackend:
    """A fresh backend for this OS. Raises WakeWordUnavailable rather than
    returning something that silently does nothing — the caller
    (voice/wake_word.py) treats that exactly like any other backend that
    failed to start: logged, and Mike stays reachable by the hotkey and the
    voice button."""
    system = platform.system()
    if system == "Darwin":
        from voice.wake.macos import MacWakeWord

        return MacWakeWord(on_wake)
    if system == "Windows":
        raise WakeWordUnavailable(
            "No wake-word backend for Windows yet. NSSpeechRecognizer has no "
            "direct Windows equivalent; a real implementation needs a "
            "lightweight always-on keyword spotter (e.g. openWakeWord, or a "
            "Windows-native voice-activation API), chosen and verified on "
            "the physical machine rather than added as a guessed dependency."
        )
    raise WakeWordUnavailable(f"No wake-word backend for {system}.")
