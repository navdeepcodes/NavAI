"""The local model through Mike's own engine (brain/engine.py).

The same model Ollama runs, spoken to over the server's OpenAI-compatible API,
so everything below is the OpenAI provider's: streaming, tool-call assembly,
error translation. What is specific to a local engine is here:

  - the model's official chat template allows one system message, at the
    start. Mike records each turn's changing context (time, focused app, the
    active mission) as its own system message, so later system messages are
    folded into the user message they preceded -- deterministically, so the
    prompt stays identical turn to turn and the cache keeps working;
  - thinking is off and the prompt cache is asked for;
  - no key, no network, and nothing to probe: capabilities are what the
    engine was started with.
"""
from __future__ import annotations

import time
from typing import Any, Iterator

from brain.providers.base import BrainError, Capabilities, StreamEvent
from brain.providers.openai_compatible import OpenAICompatibleProvider
from logs.logger import logger

# A turn's context note, carried into the user message it belongs to.
CONTEXT_OPEN = "[Context from Mike, not the user]\n"
CONTEXT_CLOSE = "\n[End of context]\n\n"


def fold_system_messages(messages: list[dict]) -> list[dict]:
    """One leading system message; any later one joins the next user message
    (or becomes a user message of its own when none follows directly)."""
    out: list[dict] = []
    pending: list[str] = []
    for i, m in enumerate(messages):
        role = m.get("role")
        if role == "system" and i == 0:
            out.append(m)
            continue
        if role == "system":
            pending.append(str(m.get("content") or ""))
            continue
        if pending and role == "user":
            m = {**m, "content": CONTEXT_OPEN + "\n\n".join(pending) + CONTEXT_CLOSE + str(m.get("content") or "")}
            pending = []
        elif pending:
            out.append({"role": "user", "content": CONTEXT_OPEN + "\n\n".join(pending) + CONTEXT_CLOSE.rstrip()})
            pending = []
        out.append(m)
    if pending:
        out.append({"role": "user", "content": CONTEXT_OPEN + "\n\n".join(pending) + CONTEXT_CLOSE.rstrip()})
    return out


class EngineProvider(OpenAICompatibleProvider):
    """Mike's own engine, and Ollama as it was if the engine can't start."""

    def __init__(self, engine, *, temperature: float = 0.7, max_tokens: int = 8192) -> None:
        super().__init__(engine.model, base_url="http://127.0.0.1:0/v1", api_key_env="",
                         name="engine", temperature=temperature, max_tokens=max_tokens,
                         context_tokens=engine.num_ctx, timeout=3600)
        self._engine = engine
        self._fallback = None

    # -- the engine, or Ollama -------------------------------------------
    def _ready(self) -> bool:
        if self._fallback is not None:
            return False
        try:
            self._engine.start()
        except Exception as exc:
            logger.warning("Mike's model engine couldn't start (%s); using Ollama instead.", exc)
            from brain.providers import get_provider
            self._fallback = get_provider(provider="ollama")
            self._caps = None
            return False
        self._base_url = self._engine.base_url + "/v1"
        return True

    def _key(self) -> str | None:
        return None

    def warm_prefix(self, system: str, tools: list[dict]) -> str:
        if not self._ready():
            return "ollama"
        return self._engine.ensure_prefix(system, tools)

    def capabilities(self) -> Capabilities:
        if self._fallback is not None:
            return self._fallback.capabilities()
        if self._caps is None:
            self._caps = Capabilities(
                model=self._model, provider=self.name, declared_text=True, declared_vision=True,
                declared_tools=True, declared_streaming=True, declared_thinking=False,
                context_tokens=self._engine.num_ctx,
                max_input_tokens=int(self._engine.num_ctx * 0.75), tool_protocol="openai-json")
        return self._caps

    def translate_error(self, exc: Exception) -> BrainError:
        if self._fallback is not None:
            return self._fallback.translate_error(exc)
        text = str(exc).lower()
        if isinstance(exc, ConnectionError) or "refused" in text or "connection" in text:
            return BrainError(kind="unavailable", retry_safe=True, detail=str(exc)[:200],
                              message="Mike's model isn't running right now. Try again in a "
                                      "moment; if it keeps happening, restart Mike.")
        return super().translate_error(exc)

    def health(self) -> BrainError | None:
        if not self._ready():
            return self._fallback.health()
        return None

    # -- requests ----------------------------------------------------------
    def _payload(self, messages, tools, stream: bool, max_tokens: int | None = None) -> dict:
        body = super()._payload(fold_system_messages(messages), tools, stream, max_tokens)
        body["chat_template_kwargs"] = {"enable_thinking": False}
        body["cache_prompt"] = True
        if tools:
            body["presence_penalty"] = 0.0
        return body

    def stream(self, messages: list[dict], tools: list[dict] | None = None, *,
               cancel: Any = None) -> Iterator[StreamEvent]:
        if not self._ready():
            yield from self._fallback.stream(messages, tools, cancel=cancel)
            return
        t0 = time.monotonic()
        yield from super().stream(messages, tools, cancel=cancel)
        logger.info("Model call (engine on %s): %.2fs | %d messages, %d tools",
                    self._engine.device.describe() if self._engine.device else "CPU",
                    time.monotonic() - t0, len(messages), len(tools or []))

    def complete(self, messages, tools=None, *, max_tokens=None):
        if not self._ready():
            return self._fallback.complete(messages, tools, max_tokens=max_tokens)
        return super().complete(messages, tools, max_tokens=max_tokens)

    def describe_image(self, *args, **kwargs):
        if not self._ready():
            return self._fallback.describe_image(*args, **kwargs)
        return super().describe_image(*args, **kwargs)
