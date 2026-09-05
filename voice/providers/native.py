"""The macOS voice. Always available, and therefore always the fallback.

This is the behaviour Mike shipped with, moved behind the provider interface
unchanged: `say` as a subprocess, stop as a terminate. It is worth being
explicit about why it stays the fallback rather than being replaced outright.

It cannot fail in the ways a neural voice can. There are no weights to load,
no generation to run away, no worker to die. It costs no resident memory and
no GPU, and it starts producing sound in about two milliseconds. Whatever
else Mike gains from a better voice, it should never lose the ability to
speak at all.
"""
from __future__ import annotations

import subprocess

from logs.logger import logger
from voice.providers.base import VoiceProvider

VOICE = "Samantha"
RATE = 185


class NativeVoice(VoiceProvider):

    name = "native"

    def __init__(self, voice: str = VOICE, rate: int = RATE) -> None:
        self._voice = voice
        self._rate = rate
        self._process: subprocess.Popen | None = None

    def available(self) -> tuple[bool, str]:
        # `say` is part of macOS. If it is missing the machine is not one
        # Mike runs on, but the check is cheap and the answer is useful.
        from shutil import which

        if which("say"):
            return True, f"macOS {self._voice}"
        return False, "the macOS `say` binary is not on this machine"

    def speak(self, text: str) -> bool:
        if not text or not text.strip():
            return False
        self.stop()
        try:
            self._process = subprocess.Popen(
                ["say", "-v", self._voice, "-r", str(self._rate), text],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception as exc:
            logger.exception("Native TTS failed: %s", exc)
            self._process = None
            return False

    def is_speaking(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def stop(self) -> None:
        if self._process is None:
            return
        try:
            self._process.terminate()
            self._process.wait(timeout=1)
        except Exception:
            try:
                self._process.kill()
            except Exception:
                pass
        self._process = None
