"""Text-to-speech command building, per platform.

voice/speaker.py owns the Speaker class (queueing, streaming, the text
sanitizer) and is otherwise platform-neutral; it only asks this module for
the argv to run and whether the engine understands inline pause markup.
"""
from __future__ import annotations

import shutil

from hostplatform import current_platform

MACOS_VOICE = "Samantha"
MACOS_RATE = 185

# spd-say rate/pitch are relative, -100..100, default 0.
LINUX_VOICE_TYPE = "female1"
LINUX_RATE = 0


def supports_inline_pauses() -> bool:
    """Whether speak_command's engine understands `[[slnc N]]`-style markup.

    Only macOS `say` does; feeding that syntax to spd-say would make it read
    the literal characters aloud, so voice/speaker.py must not add it unless
    this returns True.
    """
    return current_platform() == "Darwin"


def speak_command(text: str) -> list[str]:
    system = current_platform()
    if system == "Darwin":
        return ["say", "-v", MACOS_VOICE, "-r", str(MACOS_RATE), text]
    if system == "Linux":
        return ["spd-say", "-t", LINUX_VOICE_TYPE, "-r", str(LINUX_RATE), "--wait", text]
    raise NotImplementedError(f"Text-to-speech is not implemented on {system}.")


def stop_command() -> list[str] | None:
    """Command to cancel speech already handed to the backend.

    macOS: terminating the `say` process is enough — it owns the audio
    device directly, there is nothing left running once it's killed.
    Linux: `spd-say --wait` is just a client; speech-dispatcher keeps
    speaking after the client process dies, so it needs an explicit cancel.
    """
    if current_platform() == "Linux":
        return ["spd-say", "--cancel"]
    return None


def is_available() -> bool:
    system = current_platform()
    if system == "Darwin":
        return shutil.which("say") is not None
    if system == "Linux":
        return shutil.which("spd-say") is not None
    return False
