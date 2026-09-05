"""Tests for the model-agnostic brain boundary.

These go through the real provider and the real runtime. Where a model is
needed, a real local model answers — the point is to prove Mike behaves
correctly against actual model output, not against a mock shaped like the
answer we hoped for.

The fake providers that do appear exist only to reproduce misbehaviour a real
model cannot be asked to perform on demand (returning malformed tool calls,
declaring no tool support, being unreachable). They implement the same
contract a real provider does.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401


# ══ Canonical types and normalisation ══════════════════════

def test_provider_normalises_whatever_shape_arguments_arrive_in():
    """Providers differ on argument encoding; the runtime must never see the
    difference. A dict, a JSON string, and garbage must all resolve to either
    a usable dict or an explicit refusal."""
    from brain.providers.base import BrainProvider

    ok, problem = BrainProvider.normalise_arguments({"path": "/tmp/x"})
    assert ok == {"path": "/tmp/x"} and problem is None

    ok, problem = BrainProvider.normalise_arguments('{"path": "/tmp/x"}')
    assert ok == {"path": "/tmp/x"} and problem is None, "JSON-string args must be parsed"

    ok, problem = BrainProvider.normalise_arguments("")
    assert ok == {} and problem is None, "a tool with no arguments is legitimate"

    ok, problem = BrainProvider.normalise_arguments("not json at all")
    assert problem is not None, "unparseable arguments must be refused, not guessed at"

    ok, problem = BrainProvider.normalise_arguments("[1, 2, 3]")
    assert problem is not None, "a list is not a valid argument object"

    print("PASS: arguments are normalised or explicitly refused")


def test_capabilities_prefer_observation_over_declaration():
    """A model card is marketing; what Mike actually saw is evidence."""
    from brain.providers.base import Capabilities

    caps = Capabilities(model="m", provider="p", declared_tools=True)
    assert caps.can("tools") is True, "declaration is the fallback"

    corrected = caps.with_observation(observed_tools=False)
    assert corrected.can("tools") is False, "observation must override declaration"
    assert corrected.declared_tools is True, "the declaration is kept, not overwritten"
    print("PASS: observed capability overrides declared capability")


# ══ Context adaptation — the bug this milestone exists for ══

def test_tool_schemas_are_never_truncated_under_context_pressure():
    """The original failure: a prompt larger than the context was silently
    truncated, cutting tool schemas in half, and the model was blamed for the
    malformed calls that followed. Under pressure Mike must drop whole tools
    or whole messages — never part of a schema."""
    import json

    from brain.context_budget import plan_request
    from brain.core_tools import OLLAMA_TOOLS
    from brain.providers.base import Capabilities

    tight = Capabilities(model="small", provider="test", max_input_tokens=2500)
    messages = [{"role": "system", "content": "x" * 2000}] + [
        {"role": "user", "content": f"message {i}"} for i in range(30)
    ]

    plan = plan_request(messages, OLLAMA_TOOLS, tight)

    for tool in (plan.tools or []):
        original = next(t for t in OLLAMA_TOOLS
                        if t["function"]["name"] == tool["function"]["name"])
        assert tool == original, (
            f"{tool['function']['name']} was altered to fit — a partial schema "
            "produces wrong tool calls"
        )
    assert plan.dropped_history > 0, "history should be trimmed before anything else"
    print(
        f"PASS: under pressure dropped {plan.dropped_history} messages and "
        f"{plan.dropped_tools} whole tools; every surviving schema intact"
    )


def test_request_that_cannot_fit_fails_loudly_instead_of_being_truncated():
    from brain.context_budget import plan_request
    from brain.providers.base import Capabilities

    tiny = Capabilities(model="tiny", provider="test", max_input_tokens=800)
    plan = plan_request([{"role": "user", "content": "hello"}], None, tiny)

    assert not plan.fits
    assert plan.error.kind == "context"
    assert "too small" in plan.error.human().lower()
    print("PASS: an unworkable context fails clearly rather than silently")


def test_mikes_real_prompt_fits_the_real_configured_brain():
    """The regression that would have caught the original bug, against the
    real provider and the real tool set rather than an estimate."""
    from brain.context_budget import plan_request
    from brain.core_runtime import SYSTEM_PROMPT
    from brain.core_tools import OLLAMA_TOOLS
    from brain.providers import get_provider

    caps = get_provider().capabilities()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.replace("{date}", "today")},
        {"role": "user", "content": "find get_conn in /tmp/proj"},
    ]
    plan = plan_request(messages, OLLAMA_TOOLS, caps)

    assert plan.fits, plan.error.human() if plan.error else "?"
    assert plan.dropped_tools == 0, (
        f"Mike's own prompt should not force tools to be dropped; "
        f"{plan.estimated_tokens} tokens against a {plan.budget} budget"
    )
    print(
        f"PASS: real prompt {plan.estimated_tokens} tok fits {caps.model}'s "
        f"{plan.budget} tok budget with all {len(plan.tools)} tools"
    )


# ══ Misbehaving models must not crash Mike ═════════════════

class _MisbehavingProvider:
    """A provider whose model returns things a well-behaved one never would."""

    name = "test"

    def __init__(self, mode: str, caps=None):
        self._mode = mode
        self._caps = caps

    def capabilities(self):
        from brain.providers.base import Capabilities
        return self._caps or Capabilities(
            model="misbehaving", provider="test", declared_tools=True
        )

    def stream(self, messages, tools=None, *, cancel=None):
        from brain.providers.base import BrainError, StreamEvent

        if self._mode == "malformed_tool":
            yield StreamEvent(kind="error", error=BrainError(
                kind="protocol",
                message="The model produced a tool call Mike couldn't read.",
                retry_safe=True,
            ))
        elif self._mode == "unreachable":
            yield StreamEvent(kind="error", error=BrainError(
                kind="unavailable", message="I couldn't reach the local model."
            ))
        elif self._mode == "empty":
            yield StreamEvent(kind="done")

    def complete(self, messages, tools=None):
        from brain.providers.base import ChatResult
        return ChatResult(text="")

    def health(self):
        return None

    def translate_error(self, exc):
        from brain.providers.base import BrainError
        return BrainError(kind="unknown", message="test")


def _runtime_with(provider):
    from brain.core_runtime import CoreRuntime
    rt = CoreRuntime()
    rt._brain = provider
    rt._capabilities = provider.capabilities()
    return rt


def test_malformed_tool_call_becomes_a_message_not_a_crash():
    """A model is untrusted input. Protocol failure must reach the user as a
    sentence and must never execute anything."""
    rt = _runtime_with(_MisbehavingProvider("malformed_tool"))

    events = list(rt.process_streaming("do something", confirm_callback=lambda d: True))
    kinds = {k for k, _ in events}
    text = "".join(p for k, p in events if k == "token")

    assert "tool_start" not in kinds, "a malformed call must never be executed"
    assert text.strip(), "the user must be told something, not left with silence"
    print(f"PASS: malformed tool call surfaced as text: {text.strip()[:60]!r}")


def test_unreachable_brain_reports_instead_of_raising():
    rt = _runtime_with(_MisbehavingProvider("unreachable"))
    events = list(rt.process_streaming("hello", confirm_callback=lambda d: True))
    text = "".join(p for k, p in events if k == "token")
    assert "couldn't reach" in text.lower()
    print("PASS: an unreachable brain produces a readable message")


def test_a_brain_without_tool_support_is_never_handed_tools():
    """Feeding tools to a model that cannot use them yields prose shaped like
    a tool call, which nothing can safely act on."""
    from brain.providers.base import Capabilities
    from brain.providers.ollama_provider import OllamaProvider
    from config.ollama import OLLAMA_HOST

    provider = OllamaProvider(model="pretend", host=OLLAMA_HOST)
    provider._caps = Capabilities(
        model="pretend", provider="ollama", declared_tools=False
    )

    seen = {}
    provider._client = type("C", (), {
        "chat": lambda self, **kw: seen.update(kw) or iter(()),
    })()

    list(provider.stream([{"role": "user", "content": "hi"}], tools=[{"x": 1}]))
    assert seen.get("tools") is None, "tools must be withheld from a non-tool model"
    print("PASS: tools are withheld from a model that cannot use them")


# ══ Vision ═════════════════════════════════════════════════

def test_text_only_brain_explains_it_cannot_see_rather_than_failing():
    from brain.providers.base import BrainProvider, Capabilities

    class TextOnly(BrainProvider):
        name = "test"
        def capabilities(self):
            return Capabilities(model="text-only", provider="test", declared_vision=False)
        def stream(self, messages, tools=None, *, cancel=None):
            yield from ()
        def complete(self, messages, tools=None):
            from brain.providers.base import ChatResult
            return ChatResult()
        def health(self):
            return None

    text, error = TextOnly().describe_image("/tmp/x.png", "what is this")
    assert text == ""
    assert error is not None and error.kind == "unsupported"
    assert "can't look at images" in error.human()
    print("PASS: a text-only brain degrades to a clear explanation")


def test_runtime_resolves_a_separate_vision_model_when_the_brain_cannot_see():
    """Mike must support brain+vision in one model, or split across two."""
    from brain.core_runtime import CoreRuntime

    rt = CoreRuntime()
    brain_caps = rt._brain_capabilities()
    vision_caps = rt._vision_brain().capabilities()

    assert rt._vision_available(), "vision should be available via one model or the other"
    if not brain_caps.can("vision"):
        assert vision_caps.model != brain_caps.model, (
            "a blind brain must be paired with a different vision model"
        )
    print(
        f"PASS: brain={brain_caps.model} (vision={brain_caps.can('vision')}), "
        f"vision={vision_caps.model}"
    )


# ══ Diagnostics and switching ══════════════════════════════

def test_diagnostics_report_the_brain_actually_in_use():
    """The previous version checked one constant while the runtime ran
    another, so it could report a model as available that Mike never called."""
    import brain.core_runtime as cr
    from brain.diagnostics import check_brain

    report = check_brain()
    assert report["model"] == cr.CoreRuntime()._brain_capabilities().model
    assert "capabilities" in report and "vision" in report["capabilities"]
    print(f"PASS: diagnostics report {report['provider']}/{report['model']}")


def test_switching_the_brain_does_not_change_mikes_identity_or_data():
    """The brain is replaceable; memory, projects and identity are Mike's."""
    from brain import memory_store
    from brain.providers import get_provider

    memory_store.remember("Mike's data survives a brain change", "fact")
    before = {m["content"] for m in memory_store.all_memories()}

    a = get_provider(model="some-other-brain:7b")
    b = get_provider(model="qwen3.5:9b")
    assert a is not b
    assert a.capabilities().model != b.capabilities().model

    after = {m["content"] for m in memory_store.all_memories()}
    assert before == after, "changing the brain must not touch Mike's memory"
    print(
        f"PASS: switched {a.capabilities().model} -> {b.capabilities().model}, "
        f"{len(after)} memories intact"
    )


def test_capabilities_are_read_per_model_not_assumed():
    """Proves capabilities come from the model in front of Mike rather than a
    global assumption. This is the assumption whose absence caused the Qwen3.5
    investigation.

    This used to compare qwen3:8b against qwen3.5:9b. qwen3:8b has since been
    removed from the machine, and an absent model reports vision=False --
    exactly what the real qwen3:8b reported. The comparison would therefore
    have kept passing while silently testing a missing-model fallback against
    a real one. It now contrasts a genuinely installed model with a name that
    is deliberately absent, which is a fact that stays true either way.
    """
    from brain.providers import get_provider
    from config.ollama import OLLAMA_CHAT_MODEL

    installed = get_provider(model=OLLAMA_CHAT_MODEL).capabilities()
    assert installed.can("vision"), (
        f"{OLLAMA_CHAT_MODEL} is the configured brain and does see images; "
        "if this fails the capability read is not reaching the real model"
    )

    absent = get_provider(model="definitely-not-installed:1b").capabilities()
    assert not absent.can("vision"), "an unknown model must not be assumed capable"
    assert not absent.can("tools"), "an unknown model must not be assumed capable"

    assert installed.model != absent.model
    print(
        f"PASS: {installed.model} vision={installed.can('vision')}, "
        f"absent model degrades to vision={absent.can('vision')} "
        f"tools={absent.can('tools')}"
    )


# ══ Real end-to-end through the real provider ══════════════

def test_real_provider_returns_a_canonical_tool_call():
    """The whole boundary, against a real local model: Mike's real tools go
    in, a canonical ToolCall with dict arguments comes out."""
    from brain.context_budget import plan_request
    from brain.core_runtime import SYSTEM_PROMPT
    from brain.core_tools import OLLAMA_TOOLS, check_arguments
    from brain.providers import get_provider
    from brain.providers.base import ToolCall

    brain = get_provider()
    if brain.health() is not None:
        print("SKIP: brain unavailable in this environment")
        return

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.replace("{date}", "today")},
        {"role": "user", "content": "Find where get_conn is used in /tmp/proj."},
    ]
    plan = plan_request(messages, OLLAMA_TOOLS, brain.capabilities())
    assert plan.fits

    calls: list[ToolCall] = []
    errors = []
    for event in brain.stream(plan.messages, plan.tools):
        if event.kind == "tool_call":
            calls.append(event.tool_call)
        elif event.kind == "error":
            errors.append(event.error)

    # This exercises the raw provider, below the runtime's retry, and the
    # local brain garbles its own tool-call syntax on roughly a third of
    # calls. That is a measured model property, not a boundary defect, so
    # what is asserted is that the failure arrives as a clean, retry-safe
    # BrainError rather than an exception or a half-parsed call.
    if errors:
        assert errors[0].kind == "protocol"
        assert errors[0].retry_safe, "a garbled call must be marked recoverable"
        assert not calls, "a failed parse must not also yield a tool call"
        print(f"SKIP: model garbled its tool syntax this run — reported cleanly as "
              f"{errors[0].kind}, retry_safe={errors[0].retry_safe}")
        return

    # Whether a model chooses to call a tool on any single request is its own
    # decision and is not deterministic — observed directly: one refusal in
    # three identical runs. Asserting it would make this test flaky and would
    # be measuring the model, not the boundary. What must always hold is that
    # anything it *does* return arrives canonical and usable.
    if not calls:
        print("SKIP: the model answered in prose this time; nothing to normalise")
        return

    call = calls[0]
    assert isinstance(call.arguments, dict), "arguments must arrive normalised"
    assert check_arguments(call.name, call.arguments) is None, (
        f"real model produced unusable arguments: {call.arguments}"
    )
    print(f"PASS: real provider returned {call.name}({call.arguments})")




# ══ Second provider: a genuinely different protocol ════════

def test_openai_protocol_arguments_normalise_to_the_same_canonical_form():
    """Ollama returns tool arguments as a dict; OpenAI-compatible endpoints
    return them as a JSON string. If Mike could tell the difference, the
    boundary would be decorative."""
    from brain.providers.openai_compatible import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider(
        model="test", base_url="https://example.invalid/v1", api_key_env="NOPE_KEY"
    )
    event = provider._to_tool_call("search_code", '{"query": "x", "path": "/tmp"}', "call_9")
    assert event.kind == "tool_call"
    assert event.tool_call.arguments == {"query": "x", "path": "/tmp"}
    assert event.tool_call.call_id == "call_9", "the id must survive for correlation"

    bad = provider._to_tool_call("search_code", "not json", "call_10")
    assert bad.kind == "error" and bad.error.kind == "protocol"
    print("PASS: JSON-string arguments normalise to the same canonical ToolCall")


def test_provider_never_crashes_on_an_unexpected_error_body():
    """Real regression: Gemini returns a JSON *list* on error, and the
    provider crashed with AttributeError while trying to report the failure.
    A provider that raises while explaining a failure is worse than the
    failure itself."""
    from brain.providers.openai_compatible import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider(
        model="test", base_url="https://example.invalid/v1", api_key_env="NOPE_KEY"
    )

    class FakeResponse:
        status_code = 404
        text = "[]"
        def __init__(self, payload): self._payload = payload
        def json(self): return self._payload

    for payload in ([{"error": {"message": "gone"}}], {"error": {"message": "gone"}},
                    ["plain string"], {"unexpected": True}):
        error = provider._http_error(FakeResponse(payload))
        assert error.kind in ("unavailable", "unknown"), payload
        assert error.human(), "an error must always carry a readable message"
    print("PASS: unexpected error body shapes produce errors, never exceptions")


def test_runtime_preserves_tool_call_ids_for_provider_correlation():
    """Regression: Mike dropped ToolCall.call_id when writing history, so a
    provider could not correlate a tool result with the call that produced
    it. DeepSeek rejects that outright (HTTP 400), which looked like a model
    failure and was not."""
    import inspect

    from brain.core_runtime import CoreRuntime

    source = inspect.getsource(CoreRuntime._streaming_loop)
    assert '"id": tc.call_id' in source, "assistant tool_calls must carry the call id"
    assert '"tool_call_id": tc.call_id' in source, "tool results must reference their call"
    print("PASS: canonical call ids survive into Mike's history")


def test_capability_probe_separates_supported_from_reliable():
    from brain.capability_probe import NOT_SUPPORTED, RELIABLE, SUPPORTED, _verdict

    assert _verdict(0, 2) == NOT_SUPPORTED
    assert _verdict(1, 2) == SUPPORTED, "worked once is not works every time"
    assert _verdict(2, 2) == RELIABLE
    # A run blocked by quota teaches nothing about capability.
    assert _verdict(0, 2, blocked=True) == "not_tested"
    print("PASS: probe distinguishes supported, reliable, and never-actually-tested")


def test_probe_records_evidence_that_can_be_read_back():
    from brain.capability_probe import Observation, history, record

    record(Observation("text", "reliable", 2, 2, "", 120), "testprov", "testmodel")
    rows = history(provider="testprov")
    assert rows and rows[0]["capability"] == "text"
    assert rows[0]["verdict"] == "reliable" and rows[0]["trials"] == 2
    assert rows[0]["observed_at"] > 0, "an observation needs a timestamp to be worth keeping"
    print("PASS: observations are stored with enough context to re-read")




# ══ Context quality under agency pressure ══════════════════

def test_the_users_task_survives_context_pressure():
    """Regression for a runtime bug that looked exactly like a weak model.

    Trimming worked from the front of the conversation, so the first thing
    discarded was the user's own request. Measured: after ten tool steps the
    surviving history began with an orphaned assistant tool call and the goal
    was gone — the model was executing tools with no idea what it had been
    asked to do. The system prompt and the task are now both pinned.
    """
    from brain.context_budget import plan_request
    from brain.providers.base import Capabilities

    caps = Capabilities(model="small", provider="test", max_input_tokens=3000)
    messages = [
        {"role": "system", "content": "SYSTEM RULES"},
        {"role": "user", "content": "THE ACTUAL TASK: fix the failing test"},
    ]
    for i in range(10):
        messages.append({"role": "assistant", "content": "",
                         "tool_calls": [{"id": "c", "function": {"name": "read_file",
                                                                 "arguments": {}}}]})
        messages.append({"role": "tool", "tool_call_id": "c",
                         "content": f"RESULT-{i} " + "x" * 1500})

    plan = plan_request(messages, None, caps)

    assert plan.dropped_history > 0, "this case must actually exercise trimming"
    assert any("THE ACTUAL TASK" in str(m.get("content", "")) for m in plan.messages), (
        "the user's task must never be dropped — without it the model has no goal"
    )
    assert plan.messages[0]["role"] == "system"
    assert plan.messages[1]["role"] == "user"
    print(f"PASS: task survives after dropping {plan.dropped_history} messages")


def test_trimming_never_leaves_an_orphaned_tool_result():
    """A tool result whose assistant call was trimmed is rejected outright by
    most chat APIs and is uninterpretable by any model."""
    from brain.context_budget import plan_request
    from brain.providers.base import Capabilities

    caps = Capabilities(model="small", provider="test", max_input_tokens=3000)
    messages = [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "do the thing"},
    ]
    for i in range(10):
        messages.append({"role": "assistant", "content": "",
                         "tool_calls": [{"id": "c", "function": {"name": "read_file",
                                                                 "arguments": {}}}]})
        messages.append({"role": "tool", "tool_call_id": "c", "content": "y" * 1600})

    plan = plan_request(messages, None, caps)
    history = plan.messages[2:]          # after system + pinned task
    assert not history or history[0]["role"] != "tool", (
        "history must not begin with a tool result whose call was trimmed away"
    )
    print("PASS: no orphaned tool result survives trimming")


def test_local_brain_has_room_for_a_real_agency_loop():
    """The local brain must be able to hold its own working history.

    At the previous 8192 context the budget left ~250 tokens after the prompt
    and tool schemas, so every step discarded the last one's observations —
    which is why local multi-step work failed while the same runtime scored
    well with a large-context cloud model.
    """
    import json

    from brain.context_budget import plan_request
    from brain.core_runtime import SYSTEM_PROMPT
    from brain.core_tools import OLLAMA_TOOLS
    from brain.providers import get_provider

    caps = get_provider().capabilities()
    base = [
        {"role": "system", "content": SYSTEM_PROMPT.replace("{date}", "today")},
        {"role": "user", "content": "fix the failing test"},
    ]
    plan = plan_request(base, OLLAMA_TOOLS, caps)
    headroom = plan.budget - plan.estimated_tokens

    assert plan.dropped_tools == 0, "a fresh request must offer every tool"
    assert headroom > 2000, (
        f"only {headroom} tokens left for working history on {caps.model}; "
        "an agency loop cannot remember its own observations"
    )
    print(f"PASS: {caps.model} has {headroom} tokens of working headroom")




def test_tool_surface_is_never_stripped_to_nothing():
    """Regression: a single oversized tool result filled the budget and the
    planner dropped every tool ("offering 0 of 33 tools"). A model with no
    tools cannot act and is told nothing about why. Below a floor the request
    is refused instead."""
    from brain.context_budget import MINIMUM_TOOLS_OFFERED, plan_request
    from brain.core_tools import OLLAMA_TOOLS
    from brain.providers.base import Capabilities

    caps = Capabilities(model="small", provider="test", max_input_tokens=3000)
    messages = [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "do it"},
        {"role": "assistant", "content": "",
         "tool_calls": [{"id": "c", "function": {"name": "read_file", "arguments": {}}}]},
        {"role": "tool", "tool_call_id": "c", "content": "z" * 40000},
    ]

    plan = plan_request(messages, OLLAMA_TOOLS, caps)
    offered = len(plan.tools or [])
    assert offered >= MINIMUM_TOOLS_OFFERED or not plan.fits, (
        f"model was disarmed to {offered} tools instead of refusing the request"
    )
    if not plan.fits:
        assert plan.error.kind == "context"
    print(f"PASS: never disarmed — offered {offered}, fits={plan.fits}")


def test_recoverable_model_errors_are_retried_once_before_giving_up():
    """The provider marks a garbled tool call retry_safe; nothing consumed
    that flag, so a stochastic stumble ended the turn. Measured at roughly a
    third of calls for the local brain, so recovery matters."""
    from brain.core_runtime import MAX_STREAM_RETRIES
    from brain.providers.base import BrainError, Capabilities, ChatResult, StreamEvent

    class FlakyProvider:
        """Fails the first attempt exactly as a real garbled call does, then
        succeeds — so the test proves recovery, not luck."""
        name = "test"

        def __init__(self):
            self.attempts = 0

        def capabilities(self):
            return Capabilities(model="flaky", provider="test", declared_tools=True)

        def stream(self, messages, tools=None, *, cancel=None):
            self.attempts += 1
            if self.attempts == 1:
                yield StreamEvent(kind="error", error=BrainError(
                    kind="protocol",
                    message="produced a tool call the server couldn't parse.",
                    retry_safe=True,
                ))
                return
            yield StreamEvent(kind="text", text="recovered and answered")
            yield StreamEvent(kind="done")

        def complete(self, messages, tools=None):
            return ChatResult(text="")

        def health(self):
            return None

        def translate_error(self, exc):
            return BrainError(kind="unknown", message="test")

    provider = FlakyProvider()
    rt = _runtime_with(provider)
    text = "".join(p for k, p in rt.process_streaming("do it", confirm_callback=lambda d: True)
                   if k == "token")

    assert provider.attempts == 2, f"expected one retry, saw {provider.attempts} attempts"
    assert "recovered and answered" in text
    assert MAX_STREAM_RETRIES >= 1
    print("PASS: a recoverable model error is retried and the turn survives")


def test_unrecoverable_errors_are_not_retried_forever():
    """Recovery must not mask a backend that is genuinely down."""
    from brain.providers.base import BrainError, Capabilities, ChatResult, StreamEvent

    class DeadProvider:
        name = "test"

        def __init__(self):
            self.attempts = 0

        def capabilities(self):
            return Capabilities(model="dead", provider="test", declared_tools=True)

        def stream(self, messages, tools=None, *, cancel=None):
            self.attempts += 1
            yield StreamEvent(kind="error", error=BrainError(
                kind="unavailable", message="I couldn't reach the model.",
                retry_safe=False,
            ))

        def complete(self, messages, tools=None):
            return ChatResult(text="")

        def health(self):
            return None

        def translate_error(self, exc):
            return BrainError(kind="unknown", message="test")

    provider = DeadProvider()
    rt = _runtime_with(provider)
    text = "".join(p for k, p in rt.process_streaming("do it", confirm_callback=lambda d: True)
                   if k == "token")

    assert provider.attempts == 1, "a non-retry-safe failure must not be retried"
    assert "couldn't reach" in text
    print("PASS: unrecoverable failures surface immediately")




def test_generation_cap_allows_a_reasoning_turn_to_reach_its_tool_call():
    """Regression for a runtime bug found by the endurance test.

    Mike capped generation at 300 tokens. A model that reasons before acting
    spent that budget explaining and was cut off mid-sentence, so the turn
    ended having produced no tool call at all. Confirmed directly with
    done_reason="length" at exactly 300 tokens, and visible in the benchmark:
    "find a bug and fix it" failed in both runs while the model's own summary
    showed it had correctly diagnosed the bug and was describing the fix when
    it was truncated.

    A cap costs nothing when unused — measured identical latency for a short
    reply at 300 and at 900 — so the only effect of the old value was to turn
    verbosity into total failure.
    """
    from brain.providers.ollama_provider import DEFAULT_NUM_PREDICT
    from brain.providers.openai_compatible import DEFAULT_MAX_TOKENS

    # Assert the constants the requests actually carry. This used to assert
    # core_runtime.GEN_OPTIONS["num_predict"], which nothing read -- the cap
    # could have regressed to 900 in both providers with this still passing.
    assert DEFAULT_NUM_PREDICT >= 4096, (
        "too small a cap truncates a reasoning turn before it can call a tool"
    )
    assert DEFAULT_MAX_TOKENS >= 4096, "the same cap applies to cloud providers"
    print(f"PASS: generation caps are local={DEFAULT_NUM_PREDICT} "
          f"cloud={DEFAULT_MAX_TOKENS} tokens")


def test_a_truncated_turn_is_reported_rather_than_accepted_silently():
    """A turn stopped by the token cap is not a finished answer. Mike used to
    treat it as one, so truncation looked like a model choosing not to act."""
    import inspect

    from brain.providers import ollama_provider

    source = inspect.getsource(ollama_provider.OllamaProvider.stream)
    assert 'done_reason' in source and 'length' in source, (
        "the provider must notice when a turn was cut off by the token cap"
    )
    print("PASS: truncation is detected and reported")




def test_step_limit_allows_a_real_multi_step_task_to_finish():
    """Regression from the endurance test. At 12 the local brain made its edit
    on the final permitted step and was stopped before it could verify;
    DeepSeek needed 13 tool calls for the same task. The limit remains a
    backstop against looping, not a budget."""
    from brain.core_runtime import MAX_AGENT_STEPS

    assert MAX_AGENT_STEPS >= 15, (
        "a real task — diagnose, edit, re-test, extend — needs more than a "
        "dozen turns; measured at 13 for a competent model"
    )
    assert MAX_AGENT_STEPS <= 40, "still bounded, or a looping model never stops"
    print(f"PASS: step limit is {MAX_AGENT_STEPS}")


# ══ generation termination ═════════════════════════════════
# A reply stopped by the token limit is not a finished reply. Both providers
# had half of this: Ollama checked its streaming path and not complete(),
# the OpenAI-compatible provider checked complete() and not its streaming
# path -- and streaming is what the runtime uses, so cloud truncation was
# invisible in normal operation. The check in complete() also referenced
# `choices` before it was assigned, so every successful non-streamed cloud
# reply raised UnboundLocalError.


def _fake_openai():
    from brain.providers.openai_compatible import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider(
        model="test", base_url="https://example.invalid/v1", api_key_env="NOPE_KEY"
    )
    provider._api_key = "fake"
    return provider


class _Response:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


def test_a_complete_cloud_reply_does_not_crash():
    """Regression: the truncation check was written above the line that reads
    `choices`, so this raised UnboundLocalError on every successful reply."""
    from unittest.mock import patch

    provider = _fake_openai()
    body = {"choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
    with patch("brain.providers.openai_compatible.requests.post",
               return_value=_Response(body)):
        result = provider.complete([{"role": "user", "content": "x"}])

    assert result.error is None, "a healthy reply must not produce an error"
    assert result.text == "hi"
    assert result.truncated is False
    print("PASS: a successful non-streamed cloud reply completes")


def test_a_truncated_cloud_reply_is_marked_truncated():
    from unittest.mock import patch

    provider = _fake_openai()
    body = {"choices": [{"message": {"content": "half a sen"},
                         "finish_reason": "length"}], "usage": {}}
    with patch("brain.providers.openai_compatible.requests.post",
               return_value=_Response(body)):
        result = provider.complete([{"role": "user", "content": "x"}])

    assert result.truncated is True, "a severed reply must not look complete"
    print("PASS: a truncated non-streamed cloud reply is flagged")


def test_both_providers_expose_truncation_the_same_way():
    """The point of the canonical types is that the runtime never has to ask
    which backend it is talking to."""
    from brain.providers.base import ChatResult, StreamEvent

    assert StreamEvent(kind="done").truncated is False
    assert StreamEvent(kind="done", truncated=True).truncated is True
    assert ChatResult().truncated is False

    import inspect

    from brain.providers import ollama_provider, openai_compatible

    for module, marker in ((ollama_provider, "done_reason"),
                           (openai_compatible, "finish_reason")):
        source = inspect.getsource(module)
        assert f'{marker}' in source, f"{module.__name__} must inspect {marker}"
        assert source.count("truncated=truncated") >= 1, (
            f"{module.__name__} must carry the flag out to the caller"
        )
    print("PASS: both providers report termination through the same field")


def test_provider_specific_termination_names_stay_inside_providers():
    """done_reason and finish_reason are backend vocabulary. The runtime reads
    the canonical flag or the boundary has leaked."""
    import inspect

    from brain import core_runtime

    source = inspect.getsource(core_runtime)
    for leaked in ("done_reason", "finish_reason"):
        assert leaked not in source, (
            f"{leaked} is provider vocabulary and must not appear in the runtime"
        )
    assert "event.truncated" in source, "the runtime must read the canonical flag"
    print("PASS: termination vocabulary stays inside the provider boundary")


if __name__ == "__main__":
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        fn()
    print("\nAll model-agnostic tests passed.")


def test_a_parse_failure_is_retried_even_after_a_preamble_sentence():
    """The bug the test above could not see, because it emitted no text.

    Models write a sentence before they call a tool — "I'll open the
    spreadsheet and work through this step by step" — and the retry rule
    treated any text as output worth protecting from duplication. So a
    recoverable parse failure ended the turn on the first attempt, and the
    retry path above was dead for the case that actually happens.

    Measured on a real spreadsheet run: one turn, zero tool calls, eleven
    seconds, task abandoned, with that exact sentence as the whole reply.

    A parse failure means the tool call never parsed, so nothing ran and
    nothing can happen twice. It is retried.
    """
    from brain.providers.base import BrainError, Capabilities, ChatResult, StreamEvent

    class ChattyThenGarbled:
        name = "test"

        def __init__(self):
            self.attempts = 0

        def capabilities(self):
            return Capabilities(model="chatty", provider="test", declared_tools=True)

        def stream(self, messages, tools=None, *, cancel=None):
            self.attempts += 1
            if self.attempts == 1:
                yield StreamEvent(
                    kind="text",
                    text="I'll open the spreadsheet and work through this step by step.",
                )
                yield StreamEvent(kind="error", error=BrainError(
                    kind="protocol",
                    message="produced a tool call the server couldn't parse.",
                    retry_safe=True,
                ))
                return
            yield StreamEvent(kind="text", text="recovered and answered")
            yield StreamEvent(kind="done")

        def complete(self, messages, tools=None):
            return ChatResult(text="")

        def health(self):
            return None

        def translate_error(self, exc):
            return BrainError(kind="unknown", message="test")

    provider = ChattyThenGarbled()
    rt = _runtime_with(provider)
    text = "".join(p for k, p in rt.process_streaming("do it", confirm_callback=lambda d: True)
                   if k == "token")

    assert provider.attempts == 2, (
        f"a preamble sentence stopped the retry: {provider.attempts} attempt(s)"
    )
    assert "recovered and answered" in text
    print("PASS: a parse failure after a preamble is still retried")


def test_a_truncated_turn_with_real_output_is_still_not_retried():
    """The guarantee the old rule was protecting, kept intact.

    A turn cut off at the generation limit may have produced a genuine
    partial answer. That is not a parse failure and nothing about it is
    safe to run twice, so it is reported rather than retried.
    """
    from brain.providers.base import BrainError, Capabilities, ChatResult, StreamEvent

    class TruncatingProvider:
        name = "test"

        def __init__(self):
            self.attempts = 0

        def capabilities(self):
            return Capabilities(model="truncating", provider="test", declared_tools=True)

        def stream(self, messages, tools=None, *, cancel=None):
            self.attempts += 1
            yield StreamEvent(kind="text", text="Here is the first half of a real answer")
            yield StreamEvent(kind="done", truncated=True)

        def complete(self, messages, tools=None):
            return ChatResult(text="")

        def health(self):
            return None

        def translate_error(self, exc):
            return BrainError(kind="unknown", message="test")

    provider = TruncatingProvider()
    rt = _runtime_with(provider)
    text = "".join(p for k, p in rt.process_streaming("do it", confirm_callback=lambda d: True)
                   if k == "token")

    assert provider.attempts == 1, "partial output must not be produced twice"
    assert "first half" in text
    print("PASS: a truncated turn carrying real output is not retried")


def test_a_parse_failure_still_gives_up_after_the_retry_budget():
    """Recovery must not become an infinite loop against a model that
    garbles every attempt."""
    from brain.core_runtime import MAX_STREAM_RETRIES
    from brain.providers.base import BrainError, Capabilities, ChatResult, StreamEvent

    class AlwaysGarbled:
        name = "test"

        def __init__(self):
            self.attempts = 0

        def capabilities(self):
            return Capabilities(model="garbled", provider="test", declared_tools=True)

        def stream(self, messages, tools=None, *, cancel=None):
            self.attempts += 1
            yield StreamEvent(kind="text", text="I'll do that now.")
            yield StreamEvent(kind="error", error=BrainError(
                kind="protocol",
                message="produced a tool call the server couldn't parse.",
                retry_safe=True,
            ))

        def complete(self, messages, tools=None):
            return ChatResult(text="")

        def health(self):
            return None

        def translate_error(self, exc):
            return BrainError(kind="unknown", message="test")

    provider = AlwaysGarbled()
    rt = _runtime_with(provider)
    text = "".join(p for k, p in rt.process_streaming("do it", confirm_callback=lambda d: True)
                   if k == "token")

    assert provider.attempts == MAX_STREAM_RETRIES + 1
    assert "couldn't parse" in text, "the user must be told what went wrong"
    print("PASS: a persistently garbled model surfaces instead of looping")
