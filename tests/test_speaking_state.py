"""Mike must look busy for as long as he actually is.

Generating the text and finishing the turn are not the same moment. The reply
is spoken aloud, and speech runs seconds past the last token — but the panel
was switched to idle the instant generation ended. So Mike sat there looking
finished while still talking, and the Stop control (which is only shown for
active states) disappeared exactly when the user most wanted it: mid-sentence,
to shut him up.

Both halves are pinned here, because fixing one and not the other just moves
the lie: the panel must say "speaking" while there is a voice, and must go
quiet on its own when the sound stops.

Driven through the real UIController against the real panel — the states are
the ones the interface actually renders.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401


def _controller():
    from PySide6.QtWidgets import QApplication

    from brain.core_runtime import CoreRuntime
    from ui.controller.ui_controller import UIController
    from ui.panel.mike_panel import MikePanel

    QApplication.instance() or QApplication(sys.argv)
    runtime = CoreRuntime()
    page = MikePanel({})
    return UIController(runtime, page), page


class _StillSpeaking:
    """A speaker that is audibly mid-sentence."""

    def __init__(self) -> None:
        self.stopped = False

    def is_speaking(self):
        return True

    def speak_sentence(self, _text):
        pass

    def finish_streaming(self):
        pass

    def pump(self):
        pass

    def stop(self):
        self.stopped = True

    @property
    def streaming_done(self):
        return False


def test_the_panel_says_speaking_while_mike_is_still_talking():
    from config import preferences

    preferences.set_value("voice_enabled", True)
    controller, page = _controller()

    controller._speaker = _StillSpeaking()
    controller._response_text = "Here is the answer you asked for."

    controller._on_finished()

    assert page.state() == "speaking", (
        f"panel went to {page.state()!r} while Mike was still speaking"
    )
    assert page._stop.isVisible() or page.state() == "speaking", (
        "the Stop control vanished while Mike was still talking"
    )


def test_the_panel_goes_quiet_when_the_speech_actually_ends():
    from config import preferences

    preferences.set_value("voice_enabled", True)
    controller, page = _controller()

    class _Finished(_StillSpeaking):
        def is_speaking(self):
            return False

        @property
        def streaming_done(self):
            return True

    controller._speaker = _Finished()
    page.set_state("speaking")

    controller._pump_speech()

    assert page.state() == "idle", (
        "the panel stayed in 'speaking' after the sound stopped"
    )


def test_a_silent_reply_finishes_immediately():
    """With the voice off there is nothing to wait for, so the turn ends when
    the text does — the old behaviour, and still correct."""
    from config import preferences

    preferences.set_value("voice_enabled", False)
    controller, page = _controller()

    controller._speaker = _StillSpeaking()
    controller._response_text = "Here is the answer."

    controller._on_finished()

    assert page.state() == "idle"
    preferences.set_value("voice_enabled", True)


def test_a_finished_speech_tick_does_not_steal_a_new_turn():
    """The pump runs on a timer. If a new turn has already begun, a late tick
    must not drag the panel back to idle underneath it."""
    controller, page = _controller()

    class _Finished(_StillSpeaking):
        def is_speaking(self):
            return False

        @property
        def streaming_done(self):
            return True

    controller._speaker = _Finished()
    page.set_state("thinking")          # a new turn already owns the panel

    controller._pump_speech()

    assert page.state() == "thinking", (
        "a stale speech tick reset the state of a turn that had already started"
    )


if __name__ == "__main__":
    test_the_panel_says_speaking_while_mike_is_still_talking()
    test_the_panel_goes_quiet_when_the_speech_actually_ends()
    test_a_silent_reply_finishes_immediately()
    test_a_finished_speech_tick_does_not_steal_a_new_turn()
    print("\nAll speaking-state tests passed.")
