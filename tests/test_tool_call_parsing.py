"""Regression matrix for tool-call interpretation at the provider boundary.

Background. qwen3.5:9b was failing roughly half of its tool calls with
"XML syntax error ... element <function> closed by </parameter>" (HTTP 500).
The investigation found the cause was not the model's competence and not
Mike's parsing: the model ships `presence_penalty 1.5`, Mike inherited it,
and a repetition penalty applied to output that is *made of* repeated
structure (<parameter=…> … </parameter>) suppresses the closing tags.

Two consequences shape these tests.

First, Ollama parses tool-call XML server-side and returns HTTP 500 on
failure, so the malformed text never crosses the network. Mike cannot
mechanically repair that class of corruption however tolerant its parser is —
the recovery has to happen in Ollama (upstream PRs #17914, #16841, #16398,
all unmerged at time of writing) or be prevented by sampling, which is what
Mike now does.

Second, everything Mike *does* receive must be handled safely. A model is
untrusted input: it can name a tool that does not exist, send arguments that
are not an object, send nothing at all, or write prose that merely looks like
markup. None of that may crash Mike, and none of it may be guessed at.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401


def _ollama_provider():
    from brain.providers.ollama_provider import OllamaProvider
    from config.ollama import OLLAMA_HOST

    return OllamaProvider(model="qwen3.5:9b", host=OLLAMA_HOST)


def _openai_provider():
    from brain.providers.openai_compatible import OpenAICompatibleProvider

    return OpenAICompatibleProvider(
        model="test", base_url="https://example.invalid/v1", api_key_env="NOPE_KEY"
    )


class _RawCall:
    """Shaped like an Ollama tool call, so the provider's own translation runs."""

    def __init__(self, name, arguments):
        self.function = type("F", (), {"name": name, "arguments": arguments})()


# ══ the fix itself ═════════════════════════════════════════

def test_tool_requests_disable_the_repetition_penalty():
    """The root-cause fix. A repetition penalty applied to structured output
    suppresses the very tags that make it parseable. Measured on qwen3.5:9b:
    7/12 requests failed while inheriting the model's presence_penalty of
    1.5, and 0/12 failed with it set to zero."""
    provider = _ollama_provider()

    with_tools = provider._options_for([{"type": "function", "function": {"name": "x"}}])
    assert with_tools["presence_penalty"] == 0.0, (
        "a request carrying tools must not inherit a repetition penalty"
    )

    # Ordinary conversation keeps whatever the model's author intended.
    without_tools = provider._options_for(None)
    assert "presence_penalty" not in without_tools
    print("PASS: repetition penalty is disabled for tool requests only")


def test_the_fix_is_not_qwen_specific():
    """The rule is 'structured output should not be penalised for repeating
    structure', which holds for any model. Nothing keys off a model name."""
    import inspect

    from brain.providers import ollama_provider

    source = inspect.getsource(ollama_provider)
    logic = source.split("STRUCTURED_OUTPUT_OPTIONS = ")[1].split("class ")[0]
    assert "qwen" not in logic.lower(), "the fix must not branch on a model name"
    print("PASS: the fix is expressed as a general rule, not a model special case")


# ══ what the provider must interpret correctly ═════════════

def test_valid_single_and_multi_argument_calls():
    provider = _ollama_provider()

    single = provider._to_tool_call(_RawCall("read_file", {"path": "/tmp/a.py"}))
    assert single.kind == "tool_call"
    assert single.tool_call.arguments == {"path": "/tmp/a.py"}

    multi = provider._to_tool_call(_RawCall(
        "edit_file", {"path": "/tmp/a.py", "old_text": "a", "new_text": "b"}
    ))
    assert multi.kind == "tool_call"
    assert len(multi.tool_call.arguments) == 3
    print("PASS: valid single- and multi-argument calls are interpreted")


def test_arguments_as_a_json_string_are_accepted():
    """OpenAI-compatible endpoints encode arguments as a string; Ollama sends
    a dict. Both must reach the runtime identically."""
    provider = _openai_provider()
    event = provider._to_tool_call("search_code", '{"query": "x", "path": "/tmp"}', "c1")
    assert event.kind == "tool_call"
    assert event.tool_call.arguments == {"query": "x", "path": "/tmp"}
    print("PASS: JSON-string arguments normalise to the same canonical form")


# ══ what must be refused rather than guessed ═══════════════

def test_malformed_json_arguments_are_refused():
    provider = _openai_provider()
    event = provider._to_tool_call("read_file", "{path: /tmp/a.py", "c1")
    assert event.kind == "error"
    assert event.error.kind == "protocol"
    assert event.error.retry_safe, "a garbled call is worth one more attempt"
    print("PASS: malformed JSON arguments are refused, not repaired by guesswork")


def test_arguments_that_are_not_an_object_are_refused():
    """A list or a bare string cannot be mapped onto named parameters, and
    inventing that mapping is exactly the guessing that must not happen."""
    from brain.providers.base import BrainProvider

    for bad in ("[1, 2, 3]", '"just a string"', "42"):
        _, problem = BrainProvider.normalise_arguments(bad)
        assert problem is not None, f"{bad!r} must be refused"
    print("PASS: non-object arguments are refused")


def test_a_call_without_a_tool_name_is_refused():
    provider = _ollama_provider()
    for empty in (None, "", 123):
        event = provider._to_tool_call(_RawCall(empty, {"path": "/tmp"}))
        assert event.kind == "error"
        assert event.error.kind == "protocol"
    print("PASS: a nameless tool call is refused")


def test_a_structurally_broken_call_object_is_refused_not_crashed():
    provider = _ollama_provider()
    event = provider._to_tool_call(object())      # no .function at all
    assert event.kind == "error"
    assert event.error.kind == "protocol"
    print("PASS: a structurally broken call produces an error, not an exception")


def test_empty_arguments_are_legitimate():
    """Some tools genuinely take none — list_processes, open_browser."""
    provider = _ollama_provider()
    for empty in (None, "", {}):
        event = provider._to_tool_call(_RawCall("list_processes", empty))
        assert event.kind == "tool_call", f"{empty!r} should be an empty-argument call"
        assert event.tool_call.arguments == {}
    print("PASS: a tool with no arguments is accepted")


# ══ what the runtime must refuse to execute ════════════════

def test_a_hallucinated_tool_is_never_executed():
    """The provider will happily normalise a call to a tool that does not
    exist — it cannot know Mike's inventory. The runtime must refuse it."""
    from brain.core_runtime import CoreRuntime

    rt = CoreRuntime()
    result = rt._execute_tool("summon_a_unicorn", {"colour": "blue"})
    assert result["status"] == "error"
    assert "unknown function" in result["error"].lower() or "unhandled" in result["error"].lower()
    print("PASS: a hallucinated tool is refused by the runtime")


def test_a_real_tool_called_with_wrong_parameters_is_refused_before_running():
    """The dangerous case: enough is right that it looks executable. Nothing
    may run until the arguments actually match the declared schema."""
    from brain.core_tools import check_arguments

    problem = check_arguments("run_command", {"path": "/tmp", "command": "ls"})
    assert problem is not None, "an unknown parameter must not be silently dropped"
    assert "cwd" in problem, "the message should name the correct parameter"

    missing = check_arguments("write_file", {"path": "/tmp/a.txt"})
    assert missing is not None and "content" in missing
    print("PASS: wrong or missing parameters are refused before execution")


def test_prose_that_merely_looks_like_markup_is_not_a_tool_call():
    """A model explaining XML must not have its explanation executed."""
    from brain.providers.base import BrainProvider

    prose = "You write it as <function=read_file> with a <parameter=path> block."
    _, problem = BrainProvider.normalise_arguments(prose)
    assert problem is not None, "prose must never be coerced into arguments"
    print("PASS: XML-like prose is not turned into a tool call")


def test_safety_gates_still_apply_to_every_mutating_tool():
    """No parsing change may quietly widen what runs without confirmation."""
    from brain.core_tools import needs_confirmation

    for name in ("write_file", "delete_path", "run_command", "run_background",
                 "edit_file", "multi_edit", "kill_process", "ide_apply_edit"):
        assert needs_confirmation(name, {}), f"{name} must still require confirmation"
    for name in ("read_file", "check_url", "check_syntax", "search_code"):
        assert not needs_confirmation(name, {}), f"{name} is read-only"
    print("PASS: confirmation gates are unchanged")


# ══ provider transport failures ════════════════════════════

def test_http_failure_becomes_a_readable_error():
    provider = _openai_provider()

    class FakeResponse:
        def __init__(self, code, payload):
            self.status_code = code
            self.text = str(payload)
            self._payload = payload
        def json(self):
            return self._payload

    for code, expected in ((401, "unavailable"), (429, "timeout"),
                           (500, "unavailable"), (404, "unavailable")):
        error = provider._http_error(FakeResponse(code, {"error": {"message": "x"}}))
        assert error.kind == expected, f"HTTP {code} -> {error.kind}, expected {expected}"
        assert error.human()
    print("PASS: HTTP failures map to readable, classified errors")


def test_a_server_side_parse_failure_is_reported_as_recoverable():
    """Ollama returns HTTP 500 when its own parser rejects the model's XML.
    Mike never receives the malformed text, so it cannot repair it — but it
    must classify the failure correctly so the bounded retry can act."""
    provider = _ollama_provider()
    error = provider.translate_error(
        Exception("XML syntax error on line 8: element <function> closed by "
                  "</parameter> (status code: 500)")
    )
    assert error.kind == "protocol"
    assert error.retry_safe is True
    assert "couldn't parse" in error.human()
    print("PASS: a server-side parse failure is classified as recoverable")


if __name__ == "__main__":
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        fn()
    print("\nAll tool-call parsing tests passed.")
