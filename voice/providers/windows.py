"""The Windows voice: SAPI5, always available, and therefore always the
fallback.

macOS's `say` has no path on Windows -- SAPI5 is the OS equivalent: shipped
with every Windows install, no weights to load, no worker to die, and (like
`say`) it must never be the thing that goes silent. Reached through
win32com, already a project dependency for computer/windows.py's UI
Automation and hostplatform.desktop's hotkey plumbing, rather than adding a
new one for this.

It is not as fast as `say`, and that is stated rather than hidden: measured
on this machine, a cold Speak() call takes about a second before audio
starts (the engine warming up), against `say`'s 2-5ms. Once warm, repeat
calls start immediately.
"""
from __future__ import annotations

from logs.logger import logger
from voice.providers.base import VoiceProvider

RATE = 2       # SAPI rate is -10..10, 0 is default; a touch faster reads less flat
VOICE_HINT = "Zira"  # picked if present; falls back to SAPI's own default voice

_SVSFlagsAsync = 1
_SVSFPurgeBeforeSpeak = 2
_SPRS_DONE = 1  # SpeechRunState: only value observed while genuinely idle


class WindowsVoice(VoiceProvider):

    name = "native"

    def __init__(self, voice_hint: str = VOICE_HINT, rate: int = RATE) -> None:
        self._voice_hint = voice_hint
        self._rate = rate
        self._sapi = None

    def _get_sapi(self):
        if self._sapi is None:
            import win32com.client

            sapi = win32com.client.Dispatch("SAPI.SpVoice")
            sapi.Rate = self._rate
            for voice in sapi.GetVoices():
                if self._voice_hint.lower() in voice.GetDescription().lower():
                    sapi.Voice = voice
                    break
            self._sapi = sapi
        return self._sapi

    def available(self) -> tuple[bool, str]:
        try:
            sapi = self._get_sapi()
            voices = sapi.GetVoices()
            if voices.Count == 0:
                return False, "SAPI5 reports no installed voices"
            return True, f"SAPI5 ({sapi.Voice.GetDescription()})"
        except Exception as exc:
            return False, f"SAPI5 is not available: {exc}"

    def speak(self, text: str) -> bool:
        if not text or not text.strip():
            return False
        try:
            sapi = self._get_sapi()
            # Purge-before-speak gives this the same "replaces whatever is
            # playing" semantics the base contract requires, matching
            # NativeVoice.speak() rather than SAPI's own default queueing.
            sapi.Speak(text, _SVSFlagsAsync | _SVSFPurgeBeforeSpeak)
            return True
        except Exception as exc:
            logger.exception("SAPI5 speak failed: %s", exc)
            return False

    def enqueue(self, text: str) -> bool:
        """SAPI has its own internal queue, but speak() above bypasses it
        (purge-before-speak) to match NativeVoice's replace semantics —
        so, like NativeVoice, this has no queue of its own either; Speaker
        paces it one sentence at a time."""
        if self.is_speaking():
            return False
        return self.speak(text)

    def is_speaking(self) -> bool:
        try:
            # Observed states during a real utterance: 0 (engine warming up,
            # not yet idle), 2 (speaking), a brief 3 while finishing, then 1
            # (idle). Only 1 is unambiguously "not speaking" -- treating
            # anything else as busy avoids a race where stop() is asked for
            # during the ~1s warm-up before RunningState ever reaches 2.
            return self._get_sapi().Status.RunningState != _SPRS_DONE
        except Exception:
            return False

    def stop(self) -> None:
        try:
            if self._sapi is not None:
                self._sapi.Speak("", _SVSFPurgeBeforeSpeak)
        except Exception:
            pass
