"""Voice providers, and the rule for choosing one.

The native macOS voice is always available and always the fallback. Anything
else has to prove it can speak before Mike will use it, and has to keep
proving it: a provider that fails at runtime hands the utterance back and
Mike finishes the sentence in the voice that cannot fail.
"""
from __future__ import annotations

from voice.providers.base import VoiceProvider
from voice.providers.native import NativeVoice

__all__ = ["VoiceProvider", "NativeVoice", "get_provider", "available_providers"]


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

    if requested in ("", "native", "macos", "say", "samantha"):
        return NativeVoice()

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
        return NativeVoice()

    logger.warning("Unknown voice provider %r; using the native voice.", requested)
    return NativeVoice()
