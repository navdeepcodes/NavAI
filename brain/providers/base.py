"""The boundary between Mike and whatever brain is powering him.

Mike owns identity, memory, projects, tools, safety and the agency loop. A
provider owns one thing: turning Mike's canonical request into whatever
protocol a particular model speaks, and turning that model's output back into
canonical form. Nothing above this line should know whether the brain is
Qwen on Ollama, Claude, GPT, or something that doesn't exist yet.

Two ideas drive the shape of this file.

First, a model is untrusted input. It can hallucinate a tool that doesn't
exist, emit arguments as a JSON string where a dict was expected, stop
mid-sentence, return nothing at all, or speak a tool protocol the server
can't parse. Every one of those is a normal event to be reported, never an
exception that reaches the UI as a stack trace.

Second, declared capability is not observed capability. A model card saying
"supports tools" told us nothing about whether tool calling actually works
inside Mike's real environment — we learned that the hard way when Qwen3.5 9B
appeared unable to call tools at all, and the true cause was Mike truncating
its tool schemas. Capabilities here therefore carry both what the provider
claims and what Mike has actually seen, and they are kept apart on purpose.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from typing import Any, Iterator, Literal


# ══ Canonical wire types ═══════════════════════════════════
# Deliberately plain dataclasses rather than any provider's SDK objects, so
# that swapping providers never changes what the runtime handles.


@dataclass(frozen=True)
class ToolCall:
    """One tool invocation, normalised.

    `arguments` is always a dict by the time it leaves a provider. Providers
    differ on this — some emit a dict, some a JSON string, some XML — and
    normalising at the boundary is exactly the point.
    """

    name: str
    arguments: dict[str, Any]
    call_id: str | None = None


@dataclass
class StreamEvent:
    """One thing that happened while the model was responding.

    `kind` is one of:
      text       — a chunk of assistant prose, in `text`
      tool_call  — a completed tool call, in `tool_call`
      error      — the model or provider failed, in `error`; the loop stops
      done       — the turn finished; `truncated` says whether it finished
                   because the model was done or because it ran out of room
    """

    kind: Literal["text", "tool_call", "error", "done"]
    text: str = ""
    tool_call: ToolCall | None = None
    error: "BrainError | None" = None
    # Set on a `done` event when generation stopped at the token limit rather
    # than because the model finished. Without this the runtime cannot tell a
    # complete answer from a severed one, and a turn cut off mid-tool-call
    # looks exactly like a model that chose not to act.
    truncated: bool = False


@dataclass
class ChatResult:
    """A complete, non-streamed reply."""

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    error: "BrainError | None" = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    # See StreamEvent.truncated -- same meaning for a non-streamed reply.
    truncated: bool = False


# ══ Errors ═════════════════════════════════════════════════


@dataclass
class BrainError:
    """A model or provider failure, in terms Mike can act on and a person can read.

    `kind` separates causes that call for different responses:
      unavailable   — the backend isn't reachable or the model isn't installed
      protocol      — the model emitted something the provider couldn't parse
      context       — the request doesn't fit and couldn't be made to fit
      timeout       — took too long
      cancelled     — the user stopped it
      unsupported   — the model genuinely cannot do this (e.g. no vision)
      unknown       — anything else
    """

    kind: Literal[
        "unavailable", "protocol", "context", "timeout",
        "cancelled", "unsupported", "unknown",
    ]
    message: str
    detail: str = ""
    retry_safe: bool = False

    def human(self) -> str:
        return self.message


class BrainUnavailable(RuntimeError):
    """Raised only where a caller genuinely cannot continue without a brain."""


# ══ Capabilities ═══════════════════════════════════════════


@dataclass(frozen=True)
class Capabilities:
    """What a brain can do — separated into what it claims and what Mike saw.

    `declared_*` comes from the provider/model metadata. `observed_*` is set
    only by Mike actually trying it through the real runtime, and is None
    until then. Code that must not guess should read `can(...)`, which
    prefers observation over marketing.
    """

    model: str
    provider: str

    declared_text: bool = True
    declared_vision: bool = False
    declared_tools: bool = False
    declared_streaming: bool = True
    declared_thinking: bool = False
    declared_structured_output: bool = False

    # Total window the model advertises.
    context_tokens: int = 4096
    # What Mike may actually put in a request. Not simply context_tokens:
    # a server may reserve part of the window, and a request that overruns it
    # is silently truncated rather than refused. Providers set this to the
    # figure they can actually honour.
    max_input_tokens: int = 4096

    # How this model expects tools to be expressed, e.g. "openai-json".
    # Purely informational for humans and diagnostics — nothing above the
    # provider boundary should branch on it.
    tool_protocol: str = "unknown"

    supports_cancellation: bool = True

    observed_tools: bool | None = None
    observed_vision: bool | None = None
    observed_streaming: bool | None = None
    observed_notes: tuple[str, ...] = ()

    def can(self, what: Literal["text", "vision", "tools", "streaming", "thinking"]) -> bool:
        """Observation wins over declaration; declaration is the fallback."""
        observed = {
            "tools": self.observed_tools,
            "vision": self.observed_vision,
            "streaming": self.observed_streaming,
        }.get(what)
        if observed is not None:
            return observed
        return {
            "text": self.declared_text,
            "vision": self.declared_vision,
            "tools": self.declared_tools,
            "streaming": self.declared_streaming,
            "thinking": self.declared_thinking,
        }[what]

    def with_observation(self, **kwargs: Any) -> "Capabilities":
        return replace(self, **kwargs)

    def explain(self) -> str:
        """Plain-English summary, for diagnostics and for telling a user why
        something isn't available."""
        have = [n for n in ("text", "vision", "tools", "streaming") if self.can(n)]
        lack = [n for n in ("text", "vision", "tools", "streaming") if not self.can(n)]
        parts = [f"{self.model} via {self.provider}"]
        if have:
            parts.append("supports " + ", ".join(have))
        if lack:
            parts.append("does not support " + ", ".join(lack))
        parts.append(f"context {self.context_tokens:,} tokens")
        return "; ".join(parts) + "."


# ══ Token estimation ═══════════════════════════════════════

# Deliberately crude and provider-independent: an exact count needs the
# model's own tokenizer, which not every provider exposes.
#
# Calibrated, not guessed. Mike's real system prompt plus its 30 tool schemas
# is 19,800 characters, and Ollama reported prompt_eval_count=4956 for exactly
# that prompt — 4.0 chars/token. 3.8 is used so the estimate errs slightly
# high without inventing pressure that isn't there; an over-conservative
# figure makes the planner drop tools Mike could actually have afforded.
CHARS_PER_TOKEN = 3.8


def estimate_tokens(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value)
        except (TypeError, ValueError):
            text = str(value)
    return int(len(text) / CHARS_PER_TOKEN) + 1


# ══ The provider contract ══════════════════════════════════


class BrainProvider(ABC):
    """One brain Mike can think with.

    Implementations translate at this boundary and nowhere else. They must
    not raise for ordinary model misbehaviour — a malformed tool call, an
    unreachable server, an empty reply — those are returned as BrainError so
    the runtime can decide what to do and the user gets a sentence rather
    than a traceback.
    """

    name: str = "provider"

    @abstractmethod
    def capabilities(self) -> Capabilities:
        """What this brain can do. Cheap and cached — called often."""

    @abstractmethod
    def stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        *,
        cancel: Any = None,
    ) -> Iterator[StreamEvent]:
        """Stream a reply as canonical events. Must never raise for model or
        transport failure; yield a StreamEvent(kind="error") instead."""

    @abstractmethod
    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> ChatResult:
        """One-shot reply, for callers that don't stream (summarisation,
        wrap-up). Providers without streaming may implement stream() on top
        of this so the runtime keeps working either way."""

    @abstractmethod
    def health(self) -> BrainError | None:
        """None when this brain is ready to use, otherwise the reason it isn't."""

    def translate_error(self, exc: Exception) -> BrainError:
        """Turn a backend exception into a canonical, human-readable error.

        Providers own the wording because they own the backend: only the
        Ollama provider should ever mention Ollama. This keeps
        provider-specific phrasing out of the runtime while still giving the
        user an actionable sentence.
        """
        return BrainError(kind="unknown", message="Something went wrong with the model.",
                          detail=str(exc))

    def describe_image(self, image_path: str, prompt: str,
                       max_tokens: int | None = None) -> tuple[str, BrainError | None]:
        """Vision. The default is an honest refusal rather than a crash, so a
        text-only brain degrades to 'I can't see' instead of failing."""
        caps = self.capabilities()
        return "", BrainError(
            kind="unsupported",
            message=(
                f"{caps.model} can't look at images. Switch to a vision-capable "
                "model, or set a separate vision model, to use this."
            ),
        )

    # ── shared helpers, not provider-specific ──────────────

    @staticmethod
    def normalise_arguments(raw: Any) -> tuple[dict, str | None]:
        """Coerce whatever a model produced into a dict of arguments.

        Returns (arguments, problem). A problem string means the call is not
        safe to execute — the caller must surface it rather than guess. This
        is the single place that tolerates protocol variety, so no tool and
        no part of the runtime has to.
        """
        if raw is None or raw == "":
            return {}, None
        if isinstance(raw, dict):
            return raw, None
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except (ValueError, TypeError):
                return {}, f"arguments were not valid JSON: {raw[:120]!r}"
            if isinstance(parsed, dict):
                return parsed, None
            return {}, f"arguments must be an object, got {type(parsed).__name__}"
        return {}, f"arguments must be an object, got {type(raw).__name__}"
