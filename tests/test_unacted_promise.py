"""A reply that promises an action but makes no tool call must not reach the
user as if the action happened.

Measured in the installed app: "open notepad" was answered "Opening Notepad
for you." and "type hello in notepad" with "I'll switch back to Notepad and
type it" -- no tool call either time, so nothing happened.
"""
from brain.core_runtime import _promises_unperformed_action


class _Scripted:
    """A provider that answers each call with the next scripted reply: a
    string is plain text, a (name, args) tuple is a tool call."""

    name = "test"

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def capabilities(self):
        from brain.providers.base import Capabilities
        # Mike's real context (40k), so the retry is judged on the guard,
        # not on a toy context window refusing the request.
        return Capabilities(model="scripted", provider="test", declared_tools=True,
                            context_tokens=40960, max_input_tokens=36000)

    def stream(self, messages, tools=None, *, cancel=None):
        from brain.providers.base import StreamEvent, ToolCall
        self.calls.append([dict(m) for m in messages])
        reply = self.replies.pop(0) if self.replies else "Okay."
        if isinstance(reply, tuple):
            yield StreamEvent(kind="tool_call", tool_call=ToolCall(name=reply[0], arguments=reply[1], call_id="c1"))
        else:
            yield StreamEvent(kind="text", text=reply)
        yield StreamEvent(kind="done")

    def complete(self, messages, tools=None):
        from brain.providers.base import ChatResult
        return ChatResult(text="")

    def health(self):
        return None


def _runtime(provider, monkeypatch):
    from brain.core_runtime import CoreRuntime
    rt = CoreRuntime()
    rt._brain = provider
    rt._capabilities = provider.capabilities()
    ran = []

    def execute(name, args):
        ran.append((name, args))
        if name == "open_application":
            return {"status": "success", "result": f"Opened {args.get('name')} — its window “Untitled” is open."}
        return {"status": "success", "result": "ok"}

    monkeypatch.setattr(rt, "_execute_tool", execute)
    return rt, ran


def test_promises_are_recognised():
    assert _promises_unperformed_action("Opening Notepad for you.")
    assert _promises_unperformed_action(
        "Notepad is already open, but it's showing YouTube. I'll switch back to "
        'Notepad and type "hello from mike" in it.')
    assert _promises_unperformed_action("Sure! Let me check what's in Notepad.")


def test_real_answers_are_left_alone():
    assert not _promises_unperformed_action("84.")
    assert not _promises_unperformed_action("Notepad is open.")
    assert not _promises_unperformed_action("Let me explain: mitosis makes two identical cells.")
    assert not _promises_unperformed_action("I'll open it — which browser do you want?")
    assert not _promises_unperformed_action("I opened Notepad and typed it. Anything else?")
    assert not _promises_unperformed_action("")


def test_a_promise_without_a_tool_call_gets_one_chance_to_act(monkeypatch):
    brain = _Scripted("Opening Notepad for you.", ("open_application", {"name": "notepad"}), "Notepad is open.")
    rt, ran = _runtime(brain, monkeypatch)

    events = list(rt.process_streaming("open notepad", confirm_callback=lambda d: True))

    assert ran == [("open_application", {"name": "notepad"})], "the promised action must actually run"
    assert any(k == "tool_start" for k, _ in events)
    # The runtime's note is not remembered as something the user said.
    assert not any("Mike's runtime" in str(m.get("content")) for m in rt._core.history)


def test_the_second_chance_is_given_only_once(monkeypatch):
    brain = _Scripted("I'll open Notepad.", "I'll open Notepad now.", "never reached")
    rt, ran = _runtime(brain, monkeypatch)

    list(rt.process_streaming("open notepad", confirm_callback=lambda d: True))

    assert len(brain.calls) == 2, "one retry, never a loop"
    assert ran == []


def test_bare_open_requests_are_recognised():
    from brain.core_runtime import _is_bare_open_request
    for ok in ["open notepad", "Open Notepad.", "please launch spotify", "hey mike, open calculator",
               "start the settings app"]:
        assert _is_bare_open_request(ok), ok
    for multi in ["open notepad and type: meeting at 5pm", "open notepad, then type hi",
                  "open chrome to youtube", "open the report in word", "what can you open?"]:
        assert not _is_bare_open_request(multi), multi


def test_open_an_app_finishes_without_a_second_model_call(monkeypatch):
    brain = _Scripted(("open_application", {"name": "notepad"}), "never reached")
    rt, ran = _runtime(brain, monkeypatch)

    events = list(rt.process_streaming("open notepad", confirm_callback=lambda d: True))
    text = "".join(p for k, p in events if k == "token")

    assert ran == [("open_application", {"name": "notepad"})]
    assert len(brain.calls) == 1
    assert text.strip() == "Opened Notepad."


def test_a_launch_with_no_window_is_not_reported_as_opened(monkeypatch):
    brain = _Scripted(("open_application", {"name": "notepad"}), "It's still starting.")
    rt, _ = _runtime(brain, monkeypatch)
    monkeypatch.setattr(rt, "_execute_tool", lambda name, args: {
        "status": "success", "result": "Launched notepad, but no window for it has appeared yet."})

    events = list(rt.process_streaming("open notepad", confirm_callback=lambda d: True))
    text = "".join(p for k, p in events if k == "token")

    assert len(brain.calls) == 2, "an unconfirmed launch goes back to the model"
    assert "Opened" not in text


def test_after_a_promise_the_retry_open_still_finishes_in_one_call(monkeypatch):
    brain = _Scripted("Opening Notepad for you.", ("open_application", {"name": "notepad"}), "never reached")
    rt, _ = _runtime(brain, monkeypatch)

    list(rt.process_streaming("open notepad", confirm_callback=lambda d: True))

    assert len(brain.calls) == 2


def test_open_then_more_goes_back_to_the_model(monkeypatch):
    brain = _Scripted(("open_application", {"name": "notepad"}),
                      ("type_text", {"text": "meeting at 5pm", "app": "notepad"}), "Typed it.")
    rt, ran = _runtime(brain, monkeypatch)

    list(rt.process_streaming("open notepad and type: meeting at 5pm", confirm_callback=lambda d: True))

    assert [n for n, _ in ran] == ["open_application", "type_text"]
    assert len(brain.calls) == 3


def test_typing_as_the_last_step_is_recognised():
    from brain.core_runtime import _typing_finishes_request as done
    assert done("type hello from mike in notepad", "hello from mike")
    assert done("open notepad and type: meeting at 5pm", "meeting at 5pm")
    assert done('hey mike, type "see you at 6" into the notepad window', "see you at 6")
    assert not done("type hello and press enter", "hello")
    assert not done("type hello in notepad then save it", "hello")
    assert not done("search for cats and open notepad and type hi", "hi")
    assert not done("what's 2+2", "4")


def _typing_runtime(monkeypatch, verified, message, *replies):
    brain = _Scripted(*replies)
    rt, ran = _runtime(brain, monkeypatch)
    monkeypatch.setattr(rt, "_execute_tool", lambda name, args: ran.append(name) or {
        "status": "success", "result": "typed", "verified": verified})
    events = list(rt.process_streaming(message, confirm_callback=lambda d: True))
    return brain, "".join(p for k, p in events if k == "token")


def test_verified_typing_finishes_without_a_second_model_call(monkeypatch):
    brain, text = _typing_runtime(
        monkeypatch, True, "type hello from mike in notepad",
        ("type_text", {"text": "hello from mike", "app": "notepad"}), "never reached")
    assert len(brain.calls) == 1
    assert text.strip() == 'Typed "hello from mike" into Notepad.'


def test_unverified_typing_still_goes_back_to_the_model(monkeypatch):
    brain, _ = _typing_runtime(
        monkeypatch, False, "type hello from mike in notepad",
        ("type_text", {"text": "hello from mike", "app": "notepad"}), "Let me check.", "It's there.")
    assert len(brain.calls) >= 2


def test_typing_with_more_to_do_goes_back_to_the_model(monkeypatch):
    brain, _ = _typing_runtime(
        monkeypatch, True, "type hello and press enter",
        ("type_text", {"text": "hello"}), ("press_keys", {"key": "return"}), "Done.")
    assert len(brain.calls) == 3


class _Desk:
    """A session whose open windows are the given (app, title) pairs."""

    def __init__(self, *windows):
        from computer.base import WindowInfo
        self._windows = [WindowInfo(app=a, title=t) for a, t in windows]

    def controller(self):
        return self

    def list_windows(self):
        return self._windows


def test_the_app_the_user_named_is_the_typing_target():
    from brain.core_runtime import _app_named_in_request as named
    desk = _Desk(("chrome", "YouTube - Google Chrome"), ("Notepad", "Untitled - Notepad"))
    assert named("type hello from mike in notepad", "hello from mike", desk) == "notepad"
    assert named("write 'lab at 3' into the Notepad window", "lab at 3", desk) == "Notepad"


def test_words_that_are_not_an_open_window_are_left_alone():
    from brain.core_runtime import _app_named_in_request as named
    desk = _Desk(("chrome", "YouTube - Google Chrome"), ("Notepad", "Untitled - Notepad"))
    assert named("type: see you in class", "see you in class", desk) is None
    assert named("type hello in word", "hello", desk) is None          # Word isn't open
    assert named("type hello", "hello", desk) is None


def test_an_ordinary_answer_costs_no_extra_call(monkeypatch):
    brain = _Scripted("84.")
    rt, _ = _runtime(brain, monkeypatch)

    list(rt.process_streaming("what's 12 times 7?", confirm_callback=lambda d: True))

    assert len(brain.calls) == 1
