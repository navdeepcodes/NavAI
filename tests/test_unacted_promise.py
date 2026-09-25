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
    # whatever the verb: this one slipped past a list of verbs
    assert _promises_unperformed_action(
        "Got it. I'll set up a mission for your lab report, then look at what "
        "you've written so far and fill in the missing sections.")


def test_real_answers_are_left_alone():
    assert not _promises_unperformed_action("84.")
    assert not _promises_unperformed_action("Notepad is open.")
    assert not _promises_unperformed_action("Let me explain: mitosis makes two identical cells.")
    assert not _promises_unperformed_action("I'll open it — which browser do you want?")
    assert not _promises_unperformed_action("I opened Notepad and typed it. Anything else?")
    assert not _promises_unperformed_action("")
    assert not _promises_unperformed_action("Let me know if you want the rest.")


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

    events = list(rt.process_streaming("open notepad", confirm_callback=lambda d: True))
    text = "".join(p for k, p in events if k == "token")

    assert len(brain.calls) == 2, "one retry, never a loop"
    assert ran == []
    # and the user is told it didn't happen, rather than left with the promise
    assert "haven't actually done that" in text


def test_after_an_action_the_model_says_what_happened(monkeypatch):
    """No canned reply: the model reads the verified result and answers in
    its own words -- including when the request had more in it."""
    brain = _Scripted(("open_application", {"name": "notepad"}), "Notepad's open.")
    rt, ran = _runtime(brain, monkeypatch)

    events = list(rt.process_streaming("open notepad", confirm_callback=lambda d: True))
    text = "".join(p for k, p in events if k == "token")

    assert ran == [("open_application", {"name": "notepad"})]
    assert len(brain.calls) == 2
    assert "Opened notepad" in str(brain.calls[1][-1].get("content"))   # it saw the result
    assert text.strip() == "Notepad's open."


def test_a_launch_with_no_window_is_not_reported_as_opened(monkeypatch):
    brain = _Scripted(("open_application", {"name": "notepad"}), "It's still starting.")
    rt, _ = _runtime(brain, monkeypatch)
    monkeypatch.setattr(rt, "_execute_tool", lambda name, args: {
        "status": "success", "result": "Launched notepad, but no window for it has appeared yet."})

    events = list(rt.process_streaming("open notepad", confirm_callback=lambda d: True))
    text = "".join(p for k, p in events if k == "token")

    assert len(brain.calls) == 2, "an unconfirmed launch goes back to the model"
    assert "Opened" not in text


def test_open_then_more_goes_back_to_the_model(monkeypatch):
    brain = _Scripted(("open_application", {"name": "notepad"}),
                      ("type_text", {"text": "meeting at 5pm", "app": "notepad"}), "Typed it.")
    rt, ran = _runtime(brain, monkeypatch)

    list(rt.process_streaming("open notepad and type: meeting at 5pm", confirm_callback=lambda d: True))

    assert [n for n, _ in ran] == ["open_application", "type_text"]
    assert len(brain.calls) == 3


class _Desk:
    """A controller whose open windows are (app, pid, frontmost)."""

    def __init__(self, *windows):
        from computer.base import WindowInfo
        self._windows = [WindowInfo(app=a, title=a, pid=pid, frontmost=front) for a, pid, front in windows]
        self.typed = []

    def available(self):
        return True, "available"

    def list_windows(self):
        return self._windows

    def frontmost_app(self):
        return next(w.app for w in self._windows if w.frontmost)

    def type_text(self, text):
        from computer.base import ActionResult
        self.typed.append(text)
        return ActionResult(True, "typed")


def test_typing_with_no_app_never_goes_into_mikes_own_window():
    """With no app named, keystrokes go to the window in front -- and while
    the user talks to Mike, that is Mike's own composer."""
    import os
    from computer.session import ComputerSession

    desk = _Desk(("Mike", os.getpid(), True), ("Notepad", 4242, False), ("chrome", 4343, False))
    session = ComputerSession()
    session._controller = desk
    r = session.type_text("hello from mike")
    assert r["status"] == "error" and "Nothing was typed" in r["error"]
    assert "Notepad" in r["error"] and "chrome" in r["error"]
    assert desk.typed == []


def test_typing_with_no_app_goes_to_the_app_in_front_when_it_isnt_mike():
    import os
    from computer.session import ComputerSession

    desk = _Desk(("Mike", os.getpid(), False), ("Notepad", 4242, True))
    session = ComputerSession()
    session._controller = desk
    session._focused = lambda: None
    session.type_text("hello")
    assert desk.typed == ["hello"]


def test_an_ordinary_answer_costs_no_extra_call(monkeypatch):
    brain = _Scripted("84.")
    rt, _ = _runtime(brain, monkeypatch)

    list(rt.process_streaming("what's 12 times 7?", confirm_callback=lambda d: True))

    assert len(brain.calls) == 1
