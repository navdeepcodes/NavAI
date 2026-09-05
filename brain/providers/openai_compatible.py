"""Any OpenAI-compatible chat endpoint, as a Mike brain.

This is the second provider, and it exists partly to prove the boundary: it
speaks a genuinely different protocol from Ollama. Over HTTPS instead of a
local socket, with SSE streaming instead of a Python iterator, and — the
detail that matters most — tool-call arguments arrive as a **JSON string**
rather than a dict. If Mike above the boundary needed to know that, the
abstraction would be fake. It doesn't: normalise_arguments() handles it, and
the runtime sees the same canonical ToolCall either way.

Covers OpenRouter, DeepSeek's own API, Together, Groq, vLLM, LM Studio, and
anything else exposing /chat/completions. The base URL and model are
configuration, not code.

Credentials are read from the environment at construction and never logged,
persisted, or included in any error message.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
from typing import Any, Iterator

import requests

from brain.providers.base import (
    BrainError,
    BrainProvider,
    Capabilities,
    ChatResult,
    StreamEvent,
    ToolCall,
)
from logs.logger import logger

DEFAULT_TIMEOUT = 120

# The same limit that broke file authoring on the local provider applied here
# too and was missed when that one was fixed. A tool call that creates a file
# carries the whole file in its arguments; at 900 tokens the call is cut off
# mid-argument and the turn produces nothing usable. Measured against
# DeepSeek writing one landing page: truncated at 900 and again at 4096.
DEFAULT_MAX_TOKENS = 8192


class OpenAICompatibleProvider(BrainProvider):

    def __init__(
        self,
        model: str,
        *,
        base_url: str,
        api_key_env: str,
        name: str = "openai-compatible",
        vision_model: str | None = None,
        temperature: float = 0.4,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        context_tokens: int = 32768,
        extra_headers: dict[str, str] | None = None,
        declared_vision: bool | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self.name = name
        self._model = model
        self._vision_model = vision_model or model
        self._base_url = base_url.rstrip("/")
        self._api_key_env = api_key_env
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._context_tokens = context_tokens
        self._timeout = timeout
        self._headers = {"Content-Type": "application/json", **(extra_headers or {})}
        self._declared_vision_override = declared_vision
        self._caps: Capabilities | None = None
        self._last_usage: dict[str, Any] | None = None
        # Thinking models (DeepSeek v4, for one) return reasoning_content
        # alongside a tool call and reject the next request unless it is sent
        # back: "The `reasoning_content` in the thinking mode must be passed
        # back to the API." Mike's history has no concept of that and should
        # not gain one, so the provider remembers it per tool-call id and
        # re-attaches it when replaying that assistant turn. Bounded, because
        # a conversation should not grow this without limit.
        self._reasoning: dict[str, str] = {}

    # ── credentials ────────────────────────────────────────

    def _key(self) -> str | None:
        """Read at call time, never stored on the instance, never logged.

        A real environment variable wins; otherwise the project's .env is
        consulted, which is where development credentials live (it is
        git-ignored and mode 600). Nothing here is cached or written back.
        """
        value = os.getenv(self._api_key_env)
        if value:
            return value
        try:
            from dotenv import dotenv_values
            from pathlib import Path

            env_file = Path(__file__).resolve().parents[2] / ".env"
            if env_file.exists():
                return dotenv_values(env_file).get(self._api_key_env) or None
        except Exception:
            pass
        return None

    def _auth_headers(self) -> dict[str, str]:
        key = self._key()
        headers = dict(self._headers)
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return headers

    # ── capabilities ───────────────────────────────────────

    def capabilities(self) -> Capabilities:
        if self._caps is not None:
            return self._caps

        declared_vision = False
        declared_tools = True          # assumed, then corrected by probing
        context_tokens = self._context_tokens

        # Ask the endpoint what this model is, where that's supported. This is
        # still only a declaration — the probe is what turns it into evidence.
        try:
            response = requests.get(
                f"{self._base_url}/models", headers=self._auth_headers(), timeout=20
            )
            if response.status_code == 200:
                for entry in response.json().get("data", []):
                    if entry.get("id") != self._model:
                        continue
                    params = entry.get("supported_parameters") or []
                    if params:
                        declared_tools = "tools" in params
                    modalities = (entry.get("architecture") or {}).get(
                        "input_modalities"
                    ) or []
                    declared_vision = "image" in modalities
                    context_tokens = entry.get("context_length") or context_tokens
                    break
        except Exception as exc:
            logger.warning("Could not read model metadata for %s: %s", self._model, exc)

        if self._declared_vision_override is not None:
            declared_vision = self._declared_vision_override

        self._caps = Capabilities(
            model=self._model,
            provider=self.name,
            declared_text=True,
            declared_vision=declared_vision,
            declared_tools=declared_tools,
            declared_streaming=True,
            context_tokens=context_tokens,
            # Remote endpoints don't silently halve the window the way a local
            # server sharing slots does, but headroom is still left for the
            # reply and for estimation error.
            max_input_tokens=int(context_tokens * 0.75),
            tool_protocol="openai-json",
        )
        return self._caps

    def record_observation(self, **kwargs: Any) -> None:
        self._caps = self.capabilities().with_observation(**kwargs)

    def last_usage(self) -> dict[str, Any] | None:
        """Token counts from the most recent call, for cost accounting."""
        return self._last_usage

    # ── health ─────────────────────────────────────────────

    def health(self) -> BrainError | None:
        if not self._key():
            return BrainError(
                kind="unavailable",
                message=(
                    f"No API key for {self.name}. Set {self._api_key_env} in the "
                    "environment to use this brain."
                ),
            )
        try:
            response = requests.get(
                f"{self._base_url}/models", headers=self._auth_headers(), timeout=20
            )
        except Exception as exc:
            return BrainError(
                kind="unavailable",
                message=f"Couldn't reach {self.name}. Check your connection.",
                detail=str(exc)[:200],
                retry_safe=True,
            )
        if response.status_code in (401, 403):
            return BrainError(
                kind="unavailable",
                message=(
                    f"{self.name} rejected the API key. Check that "
                    f"{self._api_key_env} is set to a valid, unexpired key."
                ),
            )
        if response.status_code >= 500:
            return BrainError(
                kind="unavailable",
                message=f"{self.name} is having problems right now.",
                retry_safe=True,
            )
        return None

    # ── request building ───────────────────────────────────

    def _payload(self, messages, tools, stream: bool) -> dict:
        body: dict[str, Any] = {
            "model": self._model,
            "messages": [self._to_openai_message(m) for m in messages],
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "stream": stream,
        }
        if tools:
            body["tools"] = tools          # Mike's canonical schema is already
            body["tool_choice"] = "auto"   # OpenAI-shaped, so it passes through
        return body

    def _remember_reasoning(self, message: dict) -> None:
        reasoning = message.get("reasoning_content") or message.get("reasoning")
        if not reasoning:
            return
        for entry in (message.get("tool_calls") or []):
            call_id = entry.get("id")
            if call_id:
                self._reasoning[call_id] = reasoning
        if len(self._reasoning) > 64:
            for stale in list(self._reasoning)[:32]:
                del self._reasoning[stale]

    def _to_openai_message(self, message: dict) -> dict:
        """Translate Mike's internal message into OpenAI's wire shape.

        Mike stores tool results as {"role": "tool", "content": ...}; OpenAI
        requires a tool_call_id, and assistant tool calls carry ids and
        string-encoded arguments. Doing this here is exactly the boundary's
        job — Mike's history format never changes to suit a provider.
        """
        role = message.get("role")

        if role == "tool":
            return {
                "role": "tool",
                "tool_call_id": message.get("tool_call_id") or "call_0",
                "content": message.get("content") or "",
            }

        if role == "assistant" and message.get("tool_calls"):
            calls = []
            for index, call in enumerate(message["tool_calls"]):
                function = call.get("function", call)
                arguments = function.get("arguments")
                if not isinstance(arguments, str):
                    arguments = json.dumps(arguments or {})
                calls.append({
                    "id": call.get("id") or f"call_{index}",   # real id preferred
                    "type": "function",
                    "function": {"name": function.get("name"), "arguments": arguments},
                })
            rebuilt: dict[str, Any] = {
                "role": "assistant",
                "content": message.get("content") or "",
                "tool_calls": calls,
            }
            # Replay the reasoning the model gave us for these calls, where
            # the backend demands it. Absent for non-thinking models, and
            # harmlessly ignored by endpoints that don't use it.
            for call in calls:
                remembered = self._reasoning.get(call["id"])
                if remembered:
                    rebuilt["reasoning_content"] = remembered
                    break
            return rebuilt

        return {"role": role, "content": message.get("content") or ""}

    # ── generation ─────────────────────────────────────────

    def stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        *,
        cancel: Any = None,
    ) -> Iterator[StreamEvent]:
        caps = self.capabilities()
        if tools and not caps.can("tools"):
            tools = None

        try:
            response = requests.post(
                f"{self._base_url}/chat/completions",
                headers=self._auth_headers(),
                json=self._payload(messages, tools, stream=True),
                stream=True,
                timeout=self._timeout,
            )
        except Exception as exc:
            yield StreamEvent(kind="error", error=self.translate_error(exc))
            return

        if response.status_code != 200:
            yield StreamEvent(kind="error", error=self._http_error(response))
            return

        # Tool calls arrive in fragments across SSE deltas and must be
        # reassembled before they mean anything.
        partial: dict[int, dict] = {}
        truncated = False

        try:
            for raw_line in response.iter_lines(decode_unicode=True):
                if cancel is not None and getattr(cancel, "is_set", lambda: False)():
                    response.close()
                    yield StreamEvent(kind="done")
                    return
                if not raw_line or not raw_line.startswith("data:"):
                    continue
                data = raw_line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except ValueError:
                    continue

                if chunk.get("usage"):
                    self._last_usage = chunk["usage"]

                choices = chunk.get("choices") or []
                if not choices:
                    continue

                # complete() checked this and the streaming path did not -- and
                # streaming is what the runtime actually uses, so cloud
                # truncation was entirely invisible in normal operation.
                if choices[0].get("finish_reason") == "length":
                    truncated = True
                    logger.warning(
                        "%s stopped at the %d-token generation limit; the turn "
                        "was cut off before it finished.",
                        self._model, self._max_tokens,
                    )

                delta = choices[0].get("delta") or {}

                if delta.get("content"):
                    yield StreamEvent(kind="text", text=delta["content"])

                for fragment in (delta.get("tool_calls") or []):
                    index = fragment.get("index", 0)
                    slot = partial.setdefault(index, {"name": "", "arguments": "", "id": None})
                    if fragment.get("id"):
                        slot["id"] = fragment["id"]
                    function = fragment.get("function") or {}
                    if function.get("name"):
                        slot["name"] += function["name"]
                    if function.get("arguments"):
                        slot["arguments"] += function["arguments"]

        except Exception as exc:
            yield StreamEvent(kind="error", error=self.translate_error(exc))
            return

        for slot in partial.values():
            yield self._to_tool_call(slot["name"], slot["arguments"], slot["id"])

        yield StreamEvent(kind="done", truncated=truncated)

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> ChatResult:
        caps = self.capabilities()
        if tools and not caps.can("tools"):
            tools = None

        try:
            response = requests.post(
                f"{self._base_url}/chat/completions",
                headers=self._auth_headers(),
                json=self._payload(messages, tools, stream=False),
                timeout=self._timeout,
            )
        except Exception as exc:
            return ChatResult(error=self.translate_error(exc))

        if response.status_code != 200:
            return ChatResult(error=self._http_error(response))

        try:
            body = response.json()
        except ValueError:
            return ChatResult(error=BrainError(
                kind="protocol",
                message=f"{self.name} returned a response Mike couldn't read.",
                retry_safe=True,
            ))

        usage = body.get("usage") or {}
        self._last_usage = usage or None

        choices = body.get("choices") or []
        if not choices:
            return ChatResult(error=BrainError(
                kind="protocol",
                message="The model returned no response at all.",
                retry_safe=True,
            ))

        # A reply stopped by the token limit is not a finished answer. Both
        # providers used to accept one as complete, so a truncated tool call
        # looked like a model that had simply chosen to stop.
        #
        # This check has to come *after* choices is read: it was originally
        # written above that line and referenced it unbound, which made every
        # successful non-streaming completion raise UnboundLocalError. The
        # streaming path is what the runtime uses day to day, so the break sat
        # in the capability probes and brain_lab benchmarks unnoticed.
        truncated = choices[0].get("finish_reason") == "length"
        if truncated:
            logger.warning(
                "%s stopped at the %d-token generation limit; the turn was cut "
                "off before it finished.",
                self._model, self._max_tokens,
            )

        message = choices[0].get("message") or {}
        self._remember_reasoning(message)
        calls: list[ToolCall] = []
        for entry in (message.get("tool_calls") or []):
            function = entry.get("function") or {}
            event = self._to_tool_call(
                function.get("name"), function.get("arguments"), entry.get("id")
            )
            if event.kind == "tool_call" and event.tool_call:
                calls.append(event.tool_call)
            elif event.kind == "error":
                return ChatResult(text=message.get("content") or "", error=event.error)

        return ChatResult(
            text=message.get("content") or "",
            tool_calls=calls,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            truncated=truncated,
        )

    # ── vision ─────────────────────────────────────────────

    def describe_image(self, image_path: str, prompt: str,
                       max_tokens: int | None = None) -> tuple[str, BrainError | None]:
        if not self.capabilities().can("vision"):
            return super().describe_image(image_path, prompt)

        try:
            with open(image_path, "rb") as handle:
                encoded = base64.b64encode(handle.read()).decode()
        except OSError as exc:
            return "", BrainError(
                kind="unknown", message="Couldn't read that image.", detail=str(exc)
            )

        mime = mimetypes.guess_type(image_path)[0] or "image/png"
        payload = {
            "model": self._vision_model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url",
                     "image_url": {"url": f"data:{mime};base64,{encoded}"}},
                ],
            }],
            "max_tokens": int(max_tokens or 400),
        }

        try:
            response = requests.post(
                f"{self._base_url}/chat/completions",
                headers=self._auth_headers(), json=payload, timeout=self._timeout,
            )
        except Exception as exc:
            return "", self.translate_error(exc)

        if response.status_code != 200:
            return "", self._http_error(response)

        try:
            body = response.json()
            self._last_usage = body.get("usage") or self._last_usage
            return (body["choices"][0]["message"].get("content") or ""), None
        except (ValueError, KeyError, IndexError) as exc:
            return "", BrainError(
                kind="protocol",
                message=f"{self.name} returned an unreadable vision response.",
                detail=str(exc),
            )

    # ── translation ────────────────────────────────────────

    def _to_tool_call(self, name: Any, raw_arguments: Any, call_id: Any) -> StreamEvent:
        if not name or not isinstance(name, str):
            return StreamEvent(kind="error", error=BrainError(
                kind="protocol",
                message="The model asked for a tool without naming it.",
                retry_safe=True,
            ))

        arguments, problem = self.normalise_arguments(raw_arguments)
        if problem:
            return StreamEvent(kind="error", error=BrainError(
                kind="protocol",
                message=f"The model's arguments for {name} weren't usable.",
                detail=problem,
                retry_safe=True,
            ))

        return StreamEvent(
            kind="tool_call",
            tool_call=ToolCall(name=name, arguments=arguments, call_id=call_id),
        )

    def _http_error(self, response) -> BrainError:
        """Map an HTTP failure to a canonical error. The response body is
        included as detail but the request — which carries the key — is not."""
        # Error bodies are not standardised across "OpenAI-compatible"
        # endpoints — Gemini returns a JSON *list*, others a dict, some plain
        # text. Anything unexpected must still produce an error, never an
        # exception: a provider that crashes while reporting a failure is
        # worse than the failure.
        try:
            body = response.json()
            if isinstance(body, dict):
                body = body.get("error", body)
            elif isinstance(body, list) and body:
                first = body[0]
                body = first.get("error", first) if isinstance(first, dict) else first
            detail = json.dumps(body)[:300]
        except (ValueError, TypeError):
            detail = (response.text or "")[:300]

        status = response.status_code
        if status in (401, 403):
            return BrainError(
                kind="unavailable",
                message=(
                    f"{self.name} rejected the API key. Check that "
                    f"{self._api_key_env} is valid."
                ),
                detail=detail,
            )
        if status == 429:
            return BrainError(
                kind="timeout",
                message=f"{self.name} is rate limiting. Wait a moment and try again.",
                detail=detail,
                retry_safe=True,
            )
        if status == 402:
            return BrainError(
                kind="unavailable",
                message=f"{self.name} reports the account is out of credit.",
                detail=detail,
            )
        if status == 404:
            return BrainError(
                kind="unavailable",
                message=f"{self._model} isn't available on {self.name}.",
                detail=detail,
            )
        if status >= 500:
            return BrainError(
                kind="unavailable",
                message=f"{self.name} had a server error.",
                detail=detail,
                retry_safe=True,
            )
        return BrainError(
            kind="unknown",
            message=f"{self.name} returned an error ({status}).",
            detail=detail,
        )

    def translate_error(self, exc: Exception) -> BrainError:
        text = str(exc)
        if isinstance(exc, requests.Timeout):
            return BrainError(
                kind="timeout",
                message="The model took too long to respond.",
                detail=text[:200],
                retry_safe=True,
            )
        if isinstance(exc, requests.ConnectionError):
            return BrainError(
                kind="unavailable",
                message=f"Couldn't reach {self.name}. Check your connection.",
                detail=text[:200],
                retry_safe=True,
            )
        return BrainError(
            kind="unknown", message="Something went wrong with the model.", detail=text[:200]
        )
