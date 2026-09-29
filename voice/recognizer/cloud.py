"""Speech-to-text in Fast mode: Cloudflare's Whisper first, local Whisper behind.

With Fast mode on, the student's own Cloudflare account runs Mike's model, and
speech can go the same way: whisper-large-v3-turbo there is a far larger model
than the small.en that fits beside everything else on a laptop, it isn't
sharing the laptop's CPU, and a few seconds of speech costs about 3 of the
day's 10,000 free neurons.

The local recognizer is never out of the loop -- the same rules as the chat
model (brain/providers/workers_ai_provider.py): not connected or paused, the
day's allowance used, no internet, or Cloudflare failing, and the same audio
goes to local Whisper on the spot. Its model is only loaded when it's needed:
while the cloud answers, those 2.2GB stay free.
"""
from __future__ import annotations

import base64
import threading
import time
from typing import Callable

from logs.logger import logger
from voice.recognizer.base import SpeechRecognizer

API = "https://api.cloudflare.com/client/v4"
MODEL = "@cf/openai/whisper-large-v3-turbo"
#: A request that takes longer than this is abandoned for the local model --
#: waiting on a slow network is worse than transcribing here.
TIMEOUT = 12
#: How long to stay local after a failure that isn't the daily allowance.
BRIEF_REST = 180


class CloudRecognizer(SpeechRecognizer):
    """Cloudflare Whisper while Fast mode is on and working; `local` otherwise."""

    name = "cloudflare-whisper"

    def __init__(self, local: SpeechRecognizer) -> None:
        self._local = local
        self._resting_until = 0.0

    # -- which one ------------------------------------------------------
    def _use_cloud(self) -> bool:
        try:
            from brain.providers import workers_ai_provider as fast
        except Exception:
            return False
        return time.time() >= self._resting_until and fast.allowance_left() and fast.fast_mode_on()

    def _rest(self, detail: str) -> None:
        from brain.providers import workers_ai_provider as fast
        if fast.allowance_gone(detail):
            logger.info("Speech-to-text: today's free Cloudflare allowance is used up; "
                        "local Whisper until it resets.")
        else:
            self._resting_until = time.time() + BRIEF_REST
            logger.info("Speech-to-text: Cloudflare didn't answer (%s); local Whisper for a "
                        "few minutes.", detail[:160])

    # -- the SpeechRecognizer contract ------------------------------------
    def available(self) -> tuple[bool, str]:
        ok, why = self._local.available()
        return (True, "Cloudflare Whisper, local Whisper behind it") if self._use_cloud() else (ok, why)

    def prewarm(self) -> None:
        # The local model is still downloaded: it's what answers offline.
        self._local.prewarm()

    def warm(self) -> None:
        """Listening started: load the local model only if it will be used."""
        if not self._use_cloud():
            warm = getattr(self._local, "warm", None)
            if warm is not None:
                warm()

    def transcribe_async(self, audio_path: str, on_done: Callable[[str], None],
                         on_error: Callable[[str], None]) -> None:
        if not self._use_cloud():
            self._local.transcribe_async(audio_path, on_done, on_error)
            return

        def run() -> None:
            t0 = time.monotonic()
            try:
                text = self._transcribe(audio_path)
            except Exception as exc:              # anything at all: local answers
                self._rest(str(exc))
                self._local.transcribe_async(audio_path, on_done, on_error)
                return
            logger.info("Speech-to-text (Cloudflare): %.2fs", time.monotonic() - t0)
            on_done(text)

        threading.Thread(target=run, name="stt-cloudflare", daemon=True).start()

    @staticmethod
    def _transcribe(audio_path: str) -> str:
        import requests

        from account import cloudflare

        token, account = cloudflare.access_token(), cloudflare.account_id()
        if not token or not account:
            raise RuntimeError("not connected")
        with open(audio_path, "rb") as fh:
            audio = base64.b64encode(fh.read()).decode("ascii")
        for attempt in range(3):
            response = requests.post(
                f"{API}/accounts/{account}/ai/run/{MODEL}",
                headers={"Authorization": f"Bearer {token}"},
                json={"audio": audio, "language": "en"}, timeout=TIMEOUT)
            # Refused: a token too new to be known everywhere, or withdrawn --
            # cloudflare.retry_token decides. Cheaper than loading 2.2GB of
            # local Whisper for this one clip.
            if response.status_code not in (401, 403) or attempt == 2:
                break
            token = cloudflare.retry_token()
            if not token:
                break
        if response.status_code != 200:
            raise RuntimeError(f"{response.status_code} {response.text[:300]}")
        body = response.json()
        result = body.get("result") or {}
        if not body.get("success", True) or "text" not in result:
            raise RuntimeError(str(body.get("errors") or body)[:300])
        return str(result.get("text") or "").strip()
