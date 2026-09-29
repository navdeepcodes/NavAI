"""While Mike writes a step out -- several files' content, streamed for many
seconds on a laptop -- the student sees which file, not "Thinking…"."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import _isolate  # noqa: F401,E402

from brain.core_tools import preparing_label  # noqa: E402
from brain.providers import openai_compatible as oc  # noqa: E402
from brain.providers.partial_json import PartialJSON  # noqa: E402

FILES = {"files": [
    {"path": "C:/hack/site/index.html", "content": "<h1>Hello \"hackathon\"</h1>\n" * 40},
    {"path": "C:/hack/site/style.css", "content": "body { background: lightblue; }\n" * 40},
]}


class _SSE:
    """A streamed reply: a sentence, then write_files arriving a few characters at a time."""
    status_code = 200
    encoding = None

    def __init__(self, arguments: str, piece: int = 7):
        lines = [{"choices": [{"delta": {"content": "Writing both files now."}}]},
                 {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {
                     "name": "write_files", "arguments": ""}}]}}]}]
        for i in range(0, len(arguments), piece):
            lines.append({"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {
                "arguments": arguments[i:i + piece]}}]}}]})
        self._lines = [f"data: {json.dumps(x)}" for x in lines] + ["data: [DONE]"]

    def iter_lines(self, decode_unicode=True):
        yield from self._lines

    def close(self):
        pass


def _events(monkeypatch, arguments):
    from brain.providers.workers_ai_provider import _Cloud
    monkeypatch.setattr(oc.requests, "post", lambda *a, **k: _SSE(arguments))
    cloud = _Cloud("@cf/google/gemma-4-26b-a4b-it")
    monkeypatch.setattr(cloud, "_key", lambda: "token")
    return list(cloud.stream([{"role": "user", "content": "make the site"}], [{"t": 1}]))


def test_the_file_being_written_is_named_while_it_streams(monkeypatch):
    events = _events(monkeypatch, json.dumps(FILES))
    labels = []
    for e in events:
        if e.kind == "preparing":
            label = preparing_label(e.tool_call.name, e.tool_call.arguments)
            if label and (not labels or labels[-1] != label):
                labels.append(label)
    assert labels == ["Writing index.html in site", "Writing style.css in site"]
    done = [e for e in events if e.kind == "tool_call"]
    assert done and done[0].tool_call.arguments == FILES, "the call itself arrives whole, as before"


def test_nothing_half_written_is_ever_shown(monkeypatch):
    events = _events(monkeypatch, json.dumps(FILES))
    whole = {f["path"] for f in FILES["files"]}
    for e in events:
        if e.kind == "preparing":
            for f in e.tool_call.arguments.get("files", []):
                # a file just begun is {} -- no path yet, which is true; half of one isn't
                if "path" in f:
                    assert f["path"] in whole, f"a half path was shown: {f['path']}"


def test_reading_a_long_call_costs_little():
    """Re-reading the whole text at every piece would be quadratic."""
    import time
    big = json.dumps({"files": [{"path": f"C:/p/f{i}.py", "content": "x = 1\n" * 1300}
                                for i in range(5)]})
    reader, seen, t = PartialJSON(), 0, time.perf_counter()
    for i in range(0, len(big), 5):
        reader.feed(big[i:i + 5])
        if reader.values > seen:
            seen = reader.values
            reader.value()
    assert time.perf_counter() - t < 0.5


def test_until_something_true_can_be_said_nothing_is():
    assert preparing_label("write_files", {}) == ""
    assert preparing_label("write_files", {"files": []}) == ""
    assert preparing_label("run_command", {"cwd": "C:/p"}) == "", "not 'Running:' with no command"
    assert preparing_label("run_command", {"command": "npm test"}) == "Running: npm test"


# ── on screen ────────────────────────────────────────────────────────────

def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


def test_the_handwritten_line_writes_the_step_and_holds_it():
    _app()
    from ui.workspace.thinking import ThinkingLine
    line = ThinkingLine()
    line.start()
    line.set_hint("Writing index.html in site")
    try:
        for _ in range(int(1.6 / 0.016)):
            line._on_frame()
        assert line._phase == "hold", "written in about a second and a half, not a thought's 7s"
        for _ in range(int(8 / 0.016)):        # eight more seconds
            line._on_frame()
        assert line._hint == "Writing index.html in site"
        assert line._phase == "hold", "held, not faded away for another thought"
    finally:
        line.stop()


def test_a_long_step_name_is_written_smaller_before_it_is_cut():
    _app()
    from ui.workspace import thinking
    assert thinking._fitted("Writing “index.html” in site…") == 'Writing "index.html" in site...'
    long_name = "Writing a_really_long_generated_component_file_name_for_the_dashboard.tsx in components"
    fitted = thinking._fitted(long_name)
    assert fitted.endswith("...") and len(fitted) < len(long_name)


def test_between_steps_the_card_names_the_next_one():
    _app()
    from ui.workspace.steps import StepsCard
    card = StepsCard()
    card.add_row("Reading app.py")
    card.set_thinking(True, "Writing style.css in site")
    assert card._thinking.hint == "Writing style.css in site"
    card.set_thinking(False)
    assert card._thinking.hint == ""


def test_the_corner_panel_names_the_step_too():
    _app()
    from ui.panel.mike_panel import _Thinking
    t = _Thinking()
    try:
        t.set_hint("Writing style.css in site")
        assert t._hint == "Writing style.css in site" and not t._rotate.isActive()
    finally:
        t.stop()
