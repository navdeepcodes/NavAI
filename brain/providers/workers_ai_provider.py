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
import threading
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
#: With Fast mode answering, how long after startup to prepare the local
#: model's saved prompt (when it's missing), so the first minutes stay quick.
PREPARE_AFTER = 120
_PREPARE_STOP = threading.Event()


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


#: When the day's free allowance ran out, until when -- shared by everything
#: that uses the student's Cloudflare account (the chat model, and speech-to-
#: text), so the first to find it gone spares the others a failing call.
_allowance_gone_until = 0.0


def allowance_gone(detail: str) -> bool:
    """Is this Cloudflare error the daily free allowance being used up? If so,
    it's remembered until the allowance resets (00:00 UTC)."""
    global _allowance_gone_until
    text = (detail or "").lower()
    if "allocation" in text or "neuron" in text or "4006" in text:
        _allowance_gone_until = _next_utc_midnight()
        return True
    return False


def allowance_left() -> bool:
    return time.time() >= _allowance_gone_until


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
        self._answered_last: str | None = None     # "cloud" or "local"
        self._notice: str | None = None
        self._local_primed = False

    def __getattr__(self, attr: str) -> Any:
        if attr in ("_local", "_cloud"):
            raise AttributeError(attr)      # not set yet: no recursion
        return getattr(self._local, attr)

    @property
    def local(self) -> BrainProvider:
        return self._local

    # -- which one --------------------------------------------------------
    def _use_cloud(self) -> bool:
        return time.time() >= self._resting_until and allowance_left() and fast_mode_on()

    def _rest(self, error: BrainError) -> None:
        if allowance_gone(error.detail):
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
        return "resting" if time.time() < self._resting_until or not allowance_left() else "on"

    # -- saying so --------------------------------------------------------
    def _answered_by(self, who: str) -> None:
        """Note which model answered; a switch while Fast mode is on is worth
        one sentence to the student -- otherwise answers just get slow, or
        fast again, for no reason they can see."""
        was, self._answered_last = self._answered_last, who
        if was == who or not fast_mode_on():
            return
        if who == "local":
            if not allowance_left():
                until = time.strftime("%I:%M %p", time.localtime(_allowance_gone_until)).lstrip("0")
                self._notice = ("Today's free Cloudflare allowance is used up, so Mike is using "
                                f"the model on this computer until {until}. Answers will be slower.")
            else:
                self._notice = ("Mike can't reach Cloudflare right now, so he's using the model "
                                "on this computer. Answers will be slower for a few minutes.")
        elif was == "local":
            self._notice = "Fast mode is back."

    def take_notice(self) -> str | None:
        """The sentence about a switch, once."""
        notice, self._notice = self._notice, None
        return notice

    def _prime_local(self, messages: list[dict], tools: list[dict] | None) -> None:
        """Before the local model's first answer: restore its saved reading of
        Mike's prompt. Started cold it read all ~5,400 tokens again -- measured,
        the first answer after a switch took 100s; restored, it's seconds."""
        if self._local_primed:
            return
        self._local_primed = True
        warm = getattr(self._local, "warm_prefix", None)
        if warm and messages and messages[0].get("role") == "system":
            try:
                warm(str(messages[0].get("content") or ""), tools or [])
            except Exception:
                logger.debug("Couldn't restore the local model's prompt.", exc_info=True)

    def _prepare_local(self, system: str, tools: list[dict]) -> None:
        """Fast mode is answering, and the local model's reading of this prompt
        isn't saved (a new install, an update, coding switched on): read it
        now, in the background at low priority, and put the model away again
        -- so the day the allowance runs out costs seconds, not minutes."""
        engine = getattr(self._local, "_engine", None)
        if engine is None or engine.has_prefix(system, tools):
            return
        if _PREPARE_STOP.wait(PREPARE_AFTER):         # let the first minutes be quick
            return
        if not self._use_cloud() or engine.running():
            return                                    # the local model is already in use
        try:
            logger.info("Preparing the local model's reading of Mike's prompt in the background.")
            engine.start(background=True)
            engine.ensure_prefix(system, tools)
        except Exception:
            logger.warning("Couldn't prepare the local model in the background.", exc_info=True)
        finally:
            if self._use_cloud() and not self._local_primed:
                engine.stop()                         # its memory back to the student

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
                self._answered_by("cloud")
                yield first
                yield from events
                logger.info("Model call (Cloudflare %s): %.2fs | %d messages, %d tools",
                            self._cloud._model, time.monotonic() - t0, len(messages),
                            len(tools or []))
                return
            self._rest(first.error if first is not None else
                       BrainError(kind="unavailable", message="No answer from Cloudflare."))
        self._answered_by("local")
        self._prime_local(messages, tools)
        yield from self._local.stream(messages, tools, cancel=cancel)

    def complete(self, messages, tools=None, *, max_tokens=None) -> ChatResult:
        if self._use_cloud() and self._cloud._key():
            result = self._cloud.complete(messages, tools, max_tokens=max_tokens)
            if result.error is None:
                return result
            self._rest(result.error)
        self._prime_local(messages, tools)
        return self._local.complete(messages, tools, max_tokens=max_tokens)

    def describe_image(self, *args, **kwargs):
        return self._local.describe_image(*args, **kwargs)

    def warm_prefix(self, system: str, tools: list[dict]) -> str:
        """At startup: with Fast mode on, the local model isn't loaded (9GB of
        memory and a busy GPU the student gets to keep); it starts the first
        time it's needed, from its saved prompt, in seconds."""
        if self._use_cloud():
            threading.Thread(target=self._prepare_local, args=(system, tools),
                             name="prepare-local-model", daemon=True).start()
            return "cloud"
        self._local_primed = True
        warm = getattr(self._local, "warm_prefix", None)
        return warm(system, tools) if warm else "none"
