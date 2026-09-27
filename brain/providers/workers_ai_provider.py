"""Fast mode: the student's own Cloudflare Workers AI first, the local model
behind it.

Mike's local model writes about five words a second on a student laptop; the
same family of model on Cloudflare's GPUs answers a turn in seconds. The
student connects their own free Cloudflare account (account/cloudflare.py), so
the daily allowance is theirs.

The local model is never out of the loop:
  - not connected, or Fast mode paused in Settings: everything is local, as
    before -- this provider only forwards;
  - the day's free allowance used up: local until it resets (00:00 UTC);
  - no internet, or Cloudflare failing: local for a few minutes, then the
    cloud is tried again;
  - images (see_screen) always stay local: screenshots never leave the
    computer.

A failure before the cloud has said anything costs nothing visible: the same
request goes to the local model and the turn carries on.
"""
from __future__ import annotations

import datetime as _dt
import time
from dataclasses import replace
from typing import Any, Iterator

from brain.providers.base import BrainError, BrainProvider, Capabilities, ChatResult, StreamEvent
from brain.providers.engine_provider import fold_system_messages
from brain.providers.openai_compatible import OpenAICompatibleProvider
from logs.logger import logger

API = "https://api.cloudflare.com/client/v4"
#: Workers AI serves this model with a 32k-token window.
CONTEXT_TOKENS = 32768
#: How long to stay local after a failure that isn't the daily allowance.
BRIEF_REST = 180


def fast_mode_on() -> bool:
    """Connected, and not paused in Settings."""
    try:
        from config import preferences
        if not preferences.get("fast_mode", True):
            return False
        from account import cloudflare
        return cloudflare.connected()
    except Exception:
        return False


def _next_utc_midnight() -> float:
    now = _dt.datetime.now(_dt.timezone.utc)
    tomorrow = (now + _dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return tomorrow.timestamp()


class _Cloud(OpenAICompatibleProvider):
    """Workers AI's OpenAI-compatible endpoint, on the connected account."""

    def __init__(self, model: str) -> None:
        super().__init__(model, base_url=API, api_key_env="", name="Cloudflare",
                         temperature=0.7, context_tokens=CONTEXT_TOKENS, timeout=90)

    def _key(self) -> str | None:
        from account import cloudflare
        account = cloudflare.account_id()
        if not account:
            return None
        self._base_url = f"{API}/accounts/{account}/ai/v1"
        # Mike's prompt starts the same way every call; keeping a student's
        # calls on one Cloudflare machine lets it reuse that start (measured:
        # 5,056 of 5,090 prompt tokens came from its cache).
        self._headers["x-session-affinity"] = f"mike-{account[:12]}"
        return cloudflare.access_token()

    def capabilities(self) -> Capabilities:
        # Nothing to probe: the model is fixed.
        if self._caps is None:
            self._caps = Capabilities(
                model=self._model, provider="workers-ai", declared_text=True,
                declared_vision=False, declared_tools=True, declared_streaming=True,
                declared_thinking=False, context_tokens=CONTEXT_TOKENS,
                max_input_tokens=int(CONTEXT_TOKENS * 0.75), tool_protocol="openai-json")
        return self._caps

    def _payload(self, messages, tools, stream: bool, max_tokens: int | None = None) -> dict:
        body = super()._payload(fold_system_messages(messages), tools, stream, max_tokens)
        # Gemma 4 and Qwen3 think before answering unless told not to. Measured
        # on Gemma: thinking on, 1.6s a call and sometimes the whole answer
        # left in the reasoning with an empty reply; off, 10/10 right first
        # moves at 1.1s.
        body["chat_template_kwargs"] = {"enable_thinking": False}
        return body


class WorkersAIProvider(BrainProvider):
    """The cloud when Fast mode is on and working; the local brain otherwise.

    Anything this class doesn't define (warm_prefix, record_observation, ...)
    is the local brain's, so the rest of Mike sees the provider it always had.
    """

    name = "workers-ai"

    def __init__(self, local: BrainProvider, model: str) -> None:
        self._local = local
        self._cloud = _Cloud(model)
        self._resting_until = 0.0

    def __getattr__(self, attr: str) -> Any:
        if attr in ("_local", "_cloud"):
            raise AttributeError(attr)      # not set yet: no recursion
        return getattr(self._local, attr)

    @property
    def local(self) -> BrainProvider:
        return self._local

    # -- which one --------------------------------------------------------
    def _use_cloud(self) -> bool:
        return time.time() >= self._resting_until and fast_mode_on()

    def _rest(self, error: BrainError) -> None:
        detail = (error.detail or "").lower()
        if "allocation" in detail or "neuron" in detail or "4006" in detail:
            self._resting_until = _next_utc_midnight()
            logger.info("Fast mode: today's free Cloudflare allowance is used up; "
                        "the local model answers until it resets.")
        else:
            self._resting_until = time.time() + BRIEF_REST
            logger.info("Fast mode: Cloudflare didn't answer (%s: %s); the local model "
                        "answers for a few minutes.", error.kind,
                        (error.detail or error.message)[:160])

    def status(self) -> str:
        """For Settings: "off", "on", or "resting" (on, but local for now)."""
        if not fast_mode_on():
            return "off"
        return "resting" if time.time() < self._resting_until else "on"

    # -- the BrainProvider surface -----------------------------------------
    def capabilities(self) -> Capabilities:
        if not self._use_cloud():
            return self._local.capabilities()
        # Images go to the local brain, so vision is whatever it has.
        return replace(self._cloud.capabilities(),
                       declared_vision=self._local.capabilities().can("vision"))

    def health(self) -> BrainError | None:
        return None if self._use_cloud() else self._local.health()

    def translate_error(self, exc: Exception) -> BrainError:
        return self._local.translate_error(exc)

    def stream(self, messages: list[dict], tools: list[dict] | None = None, *,
               cancel: Any = None) -> Iterator[StreamEvent]:
        if self._use_cloud() and self._cloud._key():
            t0 = time.monotonic()
            events = self._cloud.stream(messages, tools, cancel=cancel)
            first = next(events, None)
            if first is not None and first.kind != "error":
                yield first
                yield from events
                logger.info("Model call (Cloudflare %s): %.2fs | %d messages, %d tools",
                            self._cloud._model, time.monotonic() - t0, len(messages),
                            len(tools or []))
                return
            self._rest(first.error if first is not None else
                       BrainError(kind="unavailable", message="No answer from Cloudflare."))
        yield from self._local.stream(messages, tools, cancel=cancel)

    def complete(self, messages, tools=None, *, max_tokens=None) -> ChatResult:
        if self._use_cloud() and self._cloud._key():
            result = self._cloud.complete(messages, tools, max_tokens=max_tokens)
            if result.error is None:
                return result
            self._rest(result.error)
        return self._local.complete(messages, tools, max_tokens=max_tokens)

    def describe_image(self, *args, **kwargs):
        return self._local.describe_image(*args, **kwargs)

    def warm_prefix(self, system: str, tools: list[dict]) -> str:
        """At startup: with Fast mode on, the local model isn't loaded (9GB of
        memory and a busy GPU the student gets to keep); it starts the first
        time it's needed, from its saved prompt, in seconds."""
        if self._use_cloud():
            return "cloud"
        warm = getattr(self._local, "warm_prefix", None)
        return warm(system, tools) if warm else "none"
