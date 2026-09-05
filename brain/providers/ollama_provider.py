"""Ollama, as a first-class Mike brain.

Everything Ollama-specific lives here: its client, its message shape, its
options, its error strings, and the one hard-won fact about its context
handling. Above this file, nothing knows Ollama exists.
"""
from __future__ import annotations

from typing import Any, Iterator

import ollama

from brain.providers.base import (
    BrainError,
    BrainProvider,
    Capabilities,
    ChatResult,
    StreamEvent,
    ToolCall,
)
from logs.logger import logger

# Ollama does not necessarily give a request the whole num_ctx. When it serves
# more than one slot it divides the window, and a prompt over the resulting
# limit is truncated silently rather than refused — observed directly in its
# own log: "truncating input prompt limit=2050 prompt=4956" with num_ctx=4096.
# Mike therefore treats only part of num_ctx as usable and plans against that.
# This is the single fact that turned "Qwen3.5 can't call tools" into "Mike
# was sending it half a tool schema".
# Measured rather than assumed, and the two measurements disagree, so the
# value is chosen to satisfy both: at num_ctx=4096 Ollama truncated at 2050
# (a half share, presumably one of two slots), yet at num_ctx=8192 it accepted
# a 4,956-token prompt whole — more than half. 0.75 sits above the prompt Mike
# actually sends at the configured 8192 while staying below the full window,
# and the reply headroom in context_budget absorbs the remaining error. If
# truncation ever reappears in the Ollama log, this is the number to lower.
USABLE_FRACTION_OF_CTX = 0.75

# What the model reports as its own trained context is often far larger than
# what is sensible to actually allocate on a laptop, so Mike sets num_ctx
# explicitly rather than inheriting it.
DEFAULT_NUM_CTX = 8192

# How many tokens a single turn may generate. 300 was too few and failed in a
# specific, damaging way: a model that reasons before acting spends the budget
# explaining and is cut off mid-sentence, so the turn ends having produced no
# tool call at all. Confirmed with done_reason="length" at exactly 300 tokens,
# and visible in the benchmark — "find a bug and fix it" failed in both runs
# while the model's own summary showed it had diagnosed the bug correctly and
# was describing the fix when it was truncated.
#
# 900 was then found too small for a different reason: authoring a file. A
# tool call that creates a real page carries the whole file in its `content`
# argument, and the model is cut off mid-argument long before it closes the
# call — so no tool call is emitted at all and the turn produces nothing.
# Measured on qwen3.5:9b asked to write one landing page:
#     num_predict =  900  ->  truncated, no tool call
#     num_predict = 2000  ->  truncated, no tool call
#     num_predict = 4000  ->  finished in 3,216 tokens, 12,140 characters written
#
# 4096 leaves room for a substantial file plus the surrounding call. It is a
# cap and not a target — short turns are unaffected and cost nothing extra —
# and it still fits inside num_ctx alongside the largest prompt Mike sends.
# 4096 still was not enough for one polished page: measured, both the local
# brain and DeepSeek were cut off mid-argument at 4096 while writing it.
# Authoring a substantial file is simply a large single generation.
DEFAULT_NUM_PREDICT = 8192

# Sampling settings a model ships with are tuned for prose, and some of them
# are actively harmful to structured output. qwen3.5:9b declares
# presence_penalty 1.5, which penalises tokens that have already appeared —
# but a tool call is *made* of repeated structure (<parameter=…>, </parameter>).
# The penalty suppresses those closing tags, the model emits malformed XML,
# and Ollama's own parser rejects it with HTTP 500 before Mike ever sees it.
#
# Measured on qwen3.5:9b with Mike's real prompt and tools:
#     inheriting the model default (1.5)  ->  7/12 requests failed
#     presence_penalty = 0.0              ->  0/12 requests failed
#     presence_penalty = 1.5 (control)    ->  7/12 requests failed
#
# Applied only when tools are in play, so ordinary conversation keeps whatever
# diversity the model's author intended. The reasoning is not Qwen-specific:
# a repetition penalty is wrong for any model asked to emit structured output.
STRUCTURED_OUTPUT_OPTIONS = {"presence_penalty": 0.0}


class OllamaProvider(BrainProvider):

    name = "ollama"

    def __init__(
        self,
        model: str,
        host: str,
        *,
        num_ctx: int = DEFAULT_NUM_CTX,
        temperature: float = 0.4,
        num_predict: int = DEFAULT_NUM_PREDICT,
        vision_model: str | None = None,
    ) -> None:
        self._model = model
        self._host = host
        self._num_ctx = num_ctx
        self._vision_model = vision_model or model
        self._options = {
            "temperature": temperature,
            "num_ctx": num_ctx,
            "num_predict": num_predict,
        }
        self._client = ollama.Client(host=host)
        self._caps: Capabilities | None = None

    # ── capabilities ───────────────────────────────────────

    def capabilities(self) -> Capabilities:
        if self._caps is not None:
            return self._caps

        declared_vision = declared_tools = declared_thinking = False
        context_tokens = self._num_ctx

        # Ollama reports real capabilities per model; use them rather than
        # assuming every local model behaves like the last one.
        try:
            info = self._client.show(self._model)
            names = {str(c).lower() for c in (info.get("capabilities") or [])}
            declared_vision = "vision" in names
            declared_tools = "tools" in names
            declared_thinking = "thinking" in names
            details = info.get("model_info") or {}
            for key, value in details.items():
                if key.endswith("context_length") and isinstance(value, int):
                    context_tokens = value
                    break
        except Exception as exc:
            logger.warning("Could not read capabilities for %s: %s", self._model, exc)

        self._caps = Capabilities(
            model=self._model,
            provider=self.name,
            declared_text=True,
            declared_vision=declared_vision,
            declared_tools=declared_tools,
            declared_streaming=True,
            declared_thinking=declared_thinking,
            context_tokens=context_tokens,
            # Deliberately derived from what Mike allocated, not from what the
            # model advertises: a 262k-token model given num_ctx=8192 can only
            # actually receive what num_ctx allows.
            max_input_tokens=int(self._num_ctx * USABLE_FRACTION_OF_CTX),
            tool_protocol="ollama-native",
        )
        return self._caps

    def record_observation(self, **kwargs: Any) -> None:
        """Lets the runtime write back what it actually saw, so declared
        capability can be corrected by evidence."""
        self._caps = self.capabilities().with_observation(**kwargs)

    # ── health ─────────────────────────────────────────────

    def health(self) -> BrainError | None:
        try:
            listed = self._client.list()
        except Exception as exc:
            return BrainError(
                kind="unavailable",
                message=(
                    "Ollama doesn't seem to be running. Open it, or run "
                    "`ollama serve` in a terminal, then try again."
                ),
                detail=str(exc),
            )

        names = {m.get("model") or m.get("name") or "" for m in (listed.get("models") or [])}
        family = self._model.split(":")[0]
        if not (self._model in names or any(n.split(":")[0] == family for n in names)):
            return BrainError(
                kind="unavailable",
                message=(
                    f"Ollama is running, but the model Mike uses ({self._model}) "
                    f"isn't pulled yet. Run `ollama pull {self._model}` in a "
                    "terminal — it only needs doing once."
                ),
            )
        return None

    # ── generation ─────────────────────────────────────────

    def _options_for(self, tools: list[dict] | None) -> dict:
        """Sampling for this request. See STRUCTURED_OUTPUT_OPTIONS."""
        if not tools:
            return self._options
        return {**self._options, **STRUCTURED_OUTPUT_OPTIONS}

    def stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        *,
        cancel: Any = None,
    ) -> Iterator[StreamEvent]:
        caps = self.capabilities()

        # Never hand tools to a model that cannot use them: it produces prose
        # that looks like a tool call and nothing can safely act on it.
        if tools and not caps.can("tools"):
            logger.info("%s has no tool support; sending a tools-free request.", self._model)
            tools = None

        truncated = False
        try:
            for chunk in self._client.chat(
                model=self._model,
                messages=messages,
                tools=tools or None,
                think=False,
                stream=True,
                options=self._options_for(tools),
            ):
                if cancel is not None and getattr(cancel, "is_set", lambda: False)():
                    yield StreamEvent(kind="done")
                    return

                message = getattr(chunk, "message", None)
                if message is None:
                    continue

                if message.content:
                    yield StreamEvent(kind="text", text=message.content)

                # A turn stopped by the token cap is not a finished answer.
                # Mike used to accept it as one, so a truncated reasoning turn
                # looked like a model that simply chose not to act.
                if getattr(chunk, "done_reason", None) == "length":
                    truncated = True
                    logger.warning(
                        "%s stopped at the %d-token generation limit; the turn was "
                        "cut off before it finished.",
                        self._model, self._options["num_predict"],
                    )

                for raw in (message.tool_calls or []):
                    event = self._to_tool_call(raw)
                    yield event

            yield StreamEvent(kind="done", truncated=truncated)

        except Exception as exc:
            yield StreamEvent(kind="error", error=self._to_error(exc))

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> ChatResult:
        caps = self.capabilities()
        if tools and not caps.can("tools"):
            tools = None
        try:
            response = self._client.chat(
                model=self._model,
                messages=messages,
                tools=tools or None,
                think=False,
                options=self._options_for(tools),
            )
        except Exception as exc:
            return ChatResult(error=self._to_error(exc))

        # The streaming path checked this and complete() did not, so a probe or
        # benchmark could read a severed reply as a finished one.
        truncated = response.get("done_reason") == "length"
        if truncated:
            logger.warning(
                "%s stopped at the %d-token generation limit; the turn was cut "
                "off before it finished.",
                self._model, self._options["num_predict"],
            )

        calls: list[ToolCall] = []
        for raw in (response.message.tool_calls or []):
            event = self._to_tool_call(raw)
            if event.kind == "tool_call" and event.tool_call:
                calls.append(event.tool_call)
            elif event.kind == "error":
                return ChatResult(text=response.message.content or "", error=event.error)

        return ChatResult(
            text=response.message.content or "",
            tool_calls=calls,
            input_tokens=response.get("prompt_eval_count"),
            output_tokens=response.get("eval_count"),
            truncated=truncated,
        )

    # ── vision ─────────────────────────────────────────────

    def describe_image(self, image_path: str, prompt: str,
                       max_tokens: int | None = None) -> tuple[str, BrainError | None]:
        try:
            response = self._client.chat(
                model=self._vision_model,
                messages=[{"role": "user", "content": prompt, "images": [image_path]}],
                think=False,
                # Vision latency is almost entirely generation: measured at a
                # flat ~16 tok/s, so the caller's budget is the one setting
                # that decides whether a look at the screen costs 3s or 10s.
                options={"temperature": 0.1, "num_predict": int(max_tokens or 96)},
            )
            return (response.message.content or ""), None
        except Exception as exc:
            return "", self._to_error(exc, model=self._vision_model)

    # ── translation ────────────────────────────────────────

    def _to_tool_call(self, raw: Any) -> StreamEvent:
        """Turn one Ollama tool call into a canonical one, or into an error.

        A model naming a tool it invented, or handing back arguments that
        aren't an object, is ordinary misbehaviour — reported, never executed
        and never raised.
        """
        try:
            name = raw.function.name
            raw_args = raw.function.arguments
        except AttributeError:
            return StreamEvent(
                kind="error",
                error=BrainError(
                    kind="protocol",
                    message="The model produced a tool call Mike couldn't read.",
                    detail=repr(raw)[:200],
                    retry_safe=True,
                ),
            )

        if not name or not isinstance(name, str):
            return StreamEvent(
                kind="error",
                error=BrainError(
                    kind="protocol",
                    message="The model asked for a tool without naming it.",
                    retry_safe=True,
                ),
            )

        arguments, problem = self.normalise_arguments(raw_args)
        if problem:
            return StreamEvent(
                kind="error",
                error=BrainError(
                    kind="protocol",
                    message=f"The model's arguments for {name} weren't usable.",
                    detail=problem,
                    retry_safe=True,
                ),
            )

        return StreamEvent(kind="tool_call", tool_call=ToolCall(name=name, arguments=arguments))

    def translate_error(self, exc: Exception) -> BrainError:
        return self._to_error(exc)

    def _to_error(self, exc: Exception, model: str | None = None) -> BrainError:
        model = model or self._model
        text = str(exc)
        low = text.lower()

        if "connection" in low or "refused" in low or "connect" in low:
            return BrainError(
                kind="unavailable",
                message="I couldn't reach the local model. Make sure Ollama is running.",
                detail=text,
                retry_safe=True,
            )
        if "not found" in low or "no such model" in low:
            return BrainError(
                kind="unavailable",
                message=(
                    f"The model {model} isn't installed. Run `ollama pull {model}`."
                ),
                detail=text,
            )
        if "timeout" in low or "deadline" in low:
            return BrainError(
                kind="timeout",
                message="That took too long. Try again, or use a smaller request.",
                detail=text,
                retry_safe=True,
            )
        # The XML/JSON parse failures Ollama returns as HTTP 500 when a model
        # emits tool syntax its parser can't read. Almost always a symptom of
        # a mangled prompt rather than a broken model, so it is retry-safe and
        # says so instead of surfacing a raw 500.
        if "syntax error" in low or "parsing failed" in low or "status code: 500" in low:
            return BrainError(
                kind="protocol",
                message=(
                    f"{model} produced a tool call the server couldn't parse."
                ),
                detail=text,
                retry_safe=True,
            )
        return BrainError(kind="unknown", message="Something went wrong with the model.", detail=text)
