"""'Opened X' is only said once X's window is actually seen."""
from computer.base import WindowInfo
from tools.system import actions


class _Windows:
    def __init__(self, *snapshots):
        self.snapshots = list(snapshots)

    def list_windows(self):
        return self.snapshots.pop(0) if len(self.snapshots) > 1 else self.snapshots[0]


def _run(monkeypatch, controller, name="notepad"):
    monkeypatch.setattr(actions, "_controller", lambda: controller)
    monkeypatch.setattr(actions.shell, "open_application", lambda n, p=None: None)
    monkeypatch.setattr(actions, "OPEN_WINDOW_TIMEOUT", 0.6)
    return actions.open_application(name)


def test_a_new_window_for_the_app_confirms_it_opened(monkeypatch):
    before = [WindowInfo(app="chrome", title="YouTube", window_id=1, frontmost=True)]
    after = before + [WindowInfo(app="Notepad", title="Untitled - Notepad", window_id=2, frontmost=True)]
    result = _run(monkeypatch, _Windows(before, before, after))
    assert result.startswith("Opened notepad")


def test_no_window_is_reported_as_not_yet_open(monkeypatch):
    only = [WindowInfo(app="chrome", title="YouTube", window_id=1, frontmost=True)]
    result = _run(monkeypatch, _Windows(only))
    assert not result.startswith("Opened")
    assert "no window" in result


def test_an_unrelated_window_that_was_already_there_does_not_count(monkeypatch):
    only = [WindowInfo(app="Notepad", title="notes - Notepad", window_id=5, frontmost=False),
            WindowInfo(app="chrome", title="YouTube", window_id=1, frontmost=True)]
    # Notepad existed before and never came forward: nothing shows the launch worked.
    result = _run(monkeypatch, _Windows(only))
    assert not result.startswith("Opened")
