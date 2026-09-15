"""Voice providers, and the rule for choosing one.

The platform's own native voice is always available and always the
fallback — `say` on macOS, SAPI5 on Windows. Anything else has to prove it
can speak before Mike will use it, and has to keep proving it: a provider
that fails at runtime hands the utterance back and Mike finishes the
sentence in the voice that cannot fail.
"""
from __future__ import annotations

import platform

from voice.providers.base import VoiceProvider
from voice.providers.native import NativeVoice

__all__ = [
    "VoiceProvider", "NativeVoice", "native_provider_class",
    "get_provider", "available_providers",
]


def native_provider_class() -> type[VoiceProvider]:
    """The class implementing this platform's unbreakable fallback voice.

    A class, not an instance: callers that need their own instance (Speaker
    holds one persistently; get_provider() below hands out a fresh one) both
    go through this one place instead of each hardcoding NativeVoice, which
    is what silently made Mike's "never goes silent" guarantee macOS-only —
    NativeVoice.available() is False wherever `say` doesn't exist, which is
    everywhere but macOS.
    """
    if platform.system() == "Windows":
        from voice.providers.windows import WindowsVoice

        return WindowsVoice
    return NativeVoice


def available_providers() -> list[str]:
    return ["native", "qwen"]


def get_provider(name: str | None = None) -> VoiceProvider:
    """The provider Mike should use, falling back rather than failing.

    A configured provider that cannot speak is a configuration problem, not a
    reason for Mike to go silent — so this logs the reason and returns the
    native voice instead.
    """
    from logs.logger import logger

    requested = (name or "native").strip().lower()

    if requested in ("", "native", "macos", "windows", "say", "sapi", "samantha"):
        return native_provider_class()()

    if requested == "qwen":
        try:
            from voice.providers.qwen import QwenVoice

            provider = QwenVoice()
            ok, why = provider.available()
            if ok:
                return provider
            logger.warning("Qwen voice unavailable (%s); using the native voice.", why)
        except Exception as exc:
            logger.warning("Qwen voice could not be created (%s); using the native voice.", exc)
        return native_provider_class()()

    logger.warning("Unknown voice provider %r; using the native voice.", requested)
    return native_provider_class()()
