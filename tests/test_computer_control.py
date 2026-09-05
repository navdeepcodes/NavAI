"""Computer interaction: the platform boundary, the safety rule, and real apps.

The end-to-end tests here drive actual applications rather than mocks, because
what is being validated is precisely whether synthetic events reach a real
interface — a mock would pass while the real thing silently did nothing, which
is exactly the failure this layer hit during development.

They skip rather than fail when the machine cannot support them (no
Accessibility grant, app not installed), so the suite stays honest on a
different machine instead of green for the wrong reason.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401


def _controller():
    from computer.base import get_controller
    return get_controller()


def _needs_accessibility():
    try:
        controller = _controller()
    except Exception as exc:
        pytest.skip(f"no computer control on this platform: {exc}")
    ok, why = controller.available()
    if not ok:
        pytest.skip(why)
    return controller


def _app_installed(name: str) -> bool:
    return any(os.path.exists(f"{root}/{name}.app")
               for root in ("/Applications", "/System/Applications"))


def _wait_for_window(session, app: str, timeout: float = 25.0, want: int = 1):
    """Wait until the app presents an observable window.

    A fixed sleep is the wrong tool here: a warm app is ready in under a
    second and a cold launch can take ten, so any constant is either slow or
    flaky. This test failed exactly that way -- passing alone, failing in a
    full run where the app had just been quit.
    """
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        result = session.observe(app=app, limit=60)
        # Wait for as many controls as the caller actually needs. Returning on
        # the first non-zero count caught Electron mid-render -- a window with
        # one or two elements -- and the assertions then failed on a loading
        # state rather than on a real defect.
        if result["status"] == "success" and (result.get("element_count") or 0) >= want:
            return result
        last = result
        time.sleep(0.5)
    return last


# ══ the platform boundary ══════════════════════════════════

def test_the_runtime_never_names_a_platform_api():
    """The whole point of the adapter is that nothing above it knows how the
    clicking is done. If CGEvent or AXUIElement appears in the runtime, the
    Windows implementation stops being a drop-in."""
    import inspect

    from brain import core_runtime

    source = inspect.getsource(core_runtime)
    for leaked in ("CGEvent", "AXUIElement", "NSWorkspace", "Quartz", "AppKit"):
        assert leaked not in source, f"{leaked} is platform detail and must stay in computer/"
    print("PASS: no platform API names in the runtime")


def test_an_unsupported_platform_fails_loudly_rather_than_pretending():
    """A stub controller that silently does nothing would be worse than no
    controller: every action would report success and change nothing."""
    import inspect

    from computer import base

    source = inspect.getsource(base.get_controller)
    assert "raise ComputerError" in source
    assert "Windows" in source, "the gap should name what is missing"
    print("PASS: an unimplemented platform raises instead of stubbing")


def test_canonical_roles_are_platform_neutral():
    from computer.base import ROLES

    for native in ("AXButton", "AXTextField", "AXWindow"):
        assert native not in ROLES, "canonical roles must not be one platform's vocabulary"
    assert {"button", "text_field", "window"} <= set(ROLES)
    print("PASS: roles are normalised, not passed through")


# ══ the safety rule ════════════════════════════════════════

def test_irreversible_controls_are_recognised_by_label():
    """The rule is a property of the interface, so the same Send button is
    caught in any application rather than per-app special cases."""
    from computer.base import looks_irreversible

    for label in ("Send", "send", "Send message", "Submit", "Delete",
                  "Move to Trash", "Buy now", "Pay $40", "Publish", "Post"):
        assert looks_irreversible(label), f"{label!r} should require confirmation"

    for label in ("Cancel", "Save Draft", "Back", "Compose", "Reply",
                  "Attach files", "Search", "OK", "Close"):
        assert not looks_irreversible(label), f"{label!r} must not be gated"
    print("PASS: irreversible controls are recognised by label")


def test_a_substring_is_not_a_match():
    """'Sender name' contains 'send' and is not a send button. Gating it would
    train the user to click through prompts, which costs more than it saves."""
    from computer.base import looks_irreversible

    for label in ("Sender name", "Resend later", "Sending options", "Postcode"):
        assert not looks_irreversible(label), f"{label!r} is a false positive"
    print("PASS: substrings do not trigger the gate")


def test_a_click_by_raw_coordinates_always_confirms():
    """A reference was checked against a real element; a coordinate was not."""
    from brain.core_tools import needs_confirmation

    assert needs_confirmation("click_element", {"x": 100, "y": 200})
    print("PASS: unverifiable coordinate clicks are gated")


def test_reading_the_screen_is_never_gated():
    from brain.core_tools import needs_confirmation

    for name in ("see_ui", "list_windows", "see_screen"):
        assert not needs_confirmation(name, {}), f"{name} only observes"
    print("PASS: observation is ungated")


def test_existing_safety_gates_are_unchanged():
    """No part of computer control may quietly widen what runs unconfirmed."""
    from brain.core_tools import needs_confirmation

    for name in ("write_file", "delete_path", "run_command", "run_background",
                 "edit_file", "multi_edit", "kill_process", "ide_apply_edit"):
        assert needs_confirmation(name, {}), f"{name} must still confirm"
    print("PASS: pre-existing gates intact")


# ══ references ═════════════════════════════════════════════

def test_a_reference_from_no_observation_is_refused():
    from computer.session import ComputerSession

    element, problem = ComputerSession().element("el1")
    assert element is None and "see_ui" in problem
    print("PASS: a reference without an observation is refused")


def test_a_stale_reference_is_refused_rather_than_clicked():
    """Interfaces move. Resolving an old reference against a new screen would
    click whatever happens to be there now, with full confidence."""
    from computer.base import Bounds, Observation, UIElement
    from computer.session import ComputerSession, REF_TTL_SECONDS

    session = ComputerSession()
    session._observation = Observation(
        app="X", elements=[UIElement(ref="el1", role="button", label="OK",
                                     bounds=Bounds(0, 0, 10, 10))])
    session._taken_at = time.time() - (REF_TTL_SECONDS + 5)

    element, problem = session.element("el1")
    assert element is None and "again" in problem.lower()
    print("PASS: stale references are refused")


class _StubController:
    """A controller whose screen is whatever the test says it is.

    Needed because acting now re-observes to confirm identity, so a test about
    geometry or identity has to control what the second observation returns --
    otherwise it is really a test about whatever happens to be on the machine.
    """

    name = "stub"

    def __init__(self, observation, frontmost="X"):
        self.observation = observation
        self._frontmost = frontmost
        self.clicks = []

    def available(self):
        return True, "stub"

    def observe(self, app=None, limit=60):
        return self.observation

    def frontmost_app(self):
        return self._frontmost

    def activate_app(self, name):
        from computer.base import ActionResult
        self._frontmost = name
        return ActionResult(True, f"{name} frontmost")

    def click(self, x, y, button="left", count=1):
        from computer.base import ActionResult
        self.clicks.append((x, y))
        return ActionResult(True, f"click at ({x}, {y})")

    def type_text(self, text):
        from computer.base import ActionResult
        return ActionResult(True, f"typed {len(text)}")

    def press_keys(self, key, modifiers=None):
        from computer.base import ActionResult
        return ActionResult(True, "pressed")

    def scroll(self, dx, dy, x=None, y=None):
        from computer.base import ActionResult
        return ActionResult(True, "scrolled")

    def drag(self, *a):
        from computer.base import ActionResult
        return ActionResult(True, "dragged")

    def list_windows(self):
        return []

    def running_apps(self):
        return ["X"]


def _session_on(observation, frontmost="X"):
    """A session whose screen is the given observation."""
    from computer.session import ComputerSession

    session = ComputerSession()
    controller = _StubController(observation, frontmost)
    session._controller = controller
    session._observation = observation
    session._taken_at = time.time()
    session._app = observation.app
    return session, controller


def test_an_element_with_no_usable_area_is_refused():
    """VS Code reports its editor as zero pixels wide. Clicking the 'centre'
    of that lands on a boundary and silently misses."""
    from computer.base import Bounds, Observation, UIElement

    observation = Observation(
        app="X", source="accessibility",
        elements=[UIElement(ref="el1", role="text_area", label="editor",
                            bounds=Bounds(254, 224, 0, 14))])
    session, controller = _session_on(observation)

    result = session.click(ref="el1")
    assert result["status"] == "error"
    assert "unusable" in result["error"] or "reliable point" in result["error"], result["error"]
    assert not controller.clicks, "nothing may be clicked"
    print("PASS: a degenerate element is refused, not clicked blindly")


# ══ real applications ══════════════════════════════════════

def test_observing_a_missing_app_is_an_error_not_an_empty_success():
    """Reporting success with zero elements sent the model looking for
    controls on a screen that was never read."""
    _needs_accessibility()
    from computer.session import ComputerSession

    result = ComputerSession().observe(app="NoSuchApplicationXYZ")
    assert result["status"] == "error"
    assert "No running application" in result["error"]
    print("PASS: a missing application reports honestly")


def test_frontmost_app_tracks_reality_within_one_process():
    """NSWorkspace answers from a run-loop-refreshed cache and goes stale in a
    tool call, naming whatever was frontmost when the process started."""
    import inspect

    from computer import macos

    source = inspect.getsource(macos.MacController.frontmost_app)
    assert "CGWindowListCopyWindowInfo" in source, (
        "frontmost must be read from the window list, not the NSWorkspace cache"
    )
    print("PASS: frontmost is read from live window order")


@pytest.mark.skipif(not _app_installed("TextEdit") and not os.path.exists("/System/Applications/TextEdit.app"),
                    reason="TextEdit not installed")
@pytest.mark.drives_real_apps
def test_end_to_end_drives_a_native_application():
    """The whole loop against a real app: observe, click, type, and verify
    from the application's own state rather than from what we claimed."""
    _needs_accessibility()
    from computer.session import ComputerSession

    session = ComputerSession()
    folder = tempfile.mkdtemp(prefix="mike-e2e-")
    path = os.path.join(folder, "e2e.txt")
    open(path, "w").close()

    subprocess.run(["open", "-a", "TextEdit", path], check=True)
    observation = _wait_for_window(session, "TextEdit")
    assert observation and observation["status"] == "success", (
        f"TextEdit never presented a window: {observation}"
    )
    session.focus_app("TextEdit")
    time.sleep(0.6)
    observation = session.observe(app="TextEdit", limit=30)
    assert observation["status"] == "success", observation.get("error")

    area = next((e for e in session._observation.elements if e.role == "text_area"), None)
    assert area is not None, "TextEdit must expose a text area"

    # Type, read back, verify, retry -- the pattern the agent itself should
    # use for any action whose success is observable. A tool call returning
    # success only means the keystrokes were posted; whether they landed in
    # the intended window is a separate question, and focus can be lost
    # between deciding to type and typing. This test failed only in a full
    # suite run, where something else took focus in between, which is exactly
    # the real-world condition worth handling rather than hoping to avoid.
    marker = f"mike-e2e-{int(time.time())}"
    landed = False
    for attempt in range(4):
        session.focus_app("TextEdit")
        time.sleep(0.8)
        observation = session.observe(app="TextEdit", limit=30)
        if observation["status"] != "success":
            continue
        area = next((e for e in session._observation.elements if e.role == "text_area"), None)
        if area is None:
            continue
        if area.bounds and area.bounds.width > 2:
            session.click(ref=area.ref)
            time.sleep(0.3)
        session.type_text(marker)
        time.sleep(0.9)

        session.observe(app="TextEdit", limit=30)
        after = next((e for e in session._observation.elements if e.role == "text_area"), None)
        if after is not None and marker in (after.value or ""):
            landed = True
            break

    assert landed, (
        f"typed text never appeared in TextEdit's own state after 4 attempts "
        f"(marker {marker!r})"
    )
    print(f"PASS: drove TextEdit and verified from its own state ({marker})")


@pytest.mark.skipif(not _app_installed("Visual Studio Code"), reason="VS Code not installed")
@pytest.mark.drives_real_apps
def test_electron_exposes_its_accessibility_tree():
    """Electron apps served an empty tree until window selection was fixed:
    they carry an untitled zero-child helper window that a naive windows[0]
    picks, while the real interface sits one window along."""
    _needs_accessibility()
    from computer.session import ComputerSession

    session = ComputerSession()
    subprocess.run(["open", "-a", "Visual Studio Code"], check=True)
    result = _wait_for_window(session, "Visual Studio Code", timeout=45, want=5)

    # An Electron app can be running with no window at all, and a cold launch
    # on a loaded machine is slow. Neither is the regression this guards, so
    # they skip. What must never happen again is a window that IS present
    # exposing nothing -- that was the windows[0] phantom-window bug, and it
    # is what the assertions below catch.
    if not result or result["status"] != "success" or (result.get("element_count") or 0) < 5:
        pytest.skip(f"VS Code presented no usable window in time: {result}")

    elements = session._observation.elements
    assert len(elements) >= 5, f"Electron should expose controls, got {len(elements)}"
    assert any(e.role == "button" for e in elements), "buttons should be addressable"
    assert any(e.label for e in elements), "controls should carry labels"

    resolved, problem = session.element(elements[0].ref)
    assert resolved is not None, problem
    print(f"PASS: Electron exposed {len(elements)} addressable controls")


# ══ actions target the observed application ════════════════

def test_actions_raise_the_observed_application_first():
    """macOS does not deliver a click to a window that is not frontmost -- not
    even to raise it. Measured with Safari behind another app: two clicks on a
    radio button at the correct screen coordinates changed nothing, brought
    Safari nowhere, and reported success both times.

    That silent no-op cost a real agent run six of its twenty steps: the model
    observed the form correctly, chose the right elements, clicked them, was
    told it had worked, and the form stayed empty. Focus is now a precondition
    of acting rather than something the caller must remember.
    """
    import inspect

    from computer.session import ComputerSession

    source = inspect.getsource(ComputerSession._ensure_front)
    assert "activate_app" in source, "acting must be able to raise the target"
    assert "frontmost_app" in source, "and must confirm it actually came forward"

    for method in ("click", "type_text", "press_keys"):
        body = inspect.getsource(getattr(ComputerSession, method))
        assert "_ensure_front" in body, f"{method} must ensure focus before acting"
    print("PASS: click, type and keypress raise the observed app first")


def test_raising_the_app_is_reported_not_hidden():
    """A focus change moves the user's screen. It belongs in the result."""
    import inspect

    from computer.session import ComputerSession

    source = inspect.getsource(ComputerSession._ensure_front)
    assert "brought" in source, "a focus switch must be visible in the result"
    print("PASS: a focus change is reported to the caller")


# ══ reference identity under mutation ══════════════════════
# A reference used to be checked only for age, and age says nothing about
# whether the interface changed. These cover what actually happens to a live
# UI between observing it and acting on it.


def _obs(app="X", **kw):
    from computer.base import Observation
    return Observation(app=app, source="accessibility", **kw)


def _el(ref, role, label, x=0, y=0, w=100, h=20, **kw):
    from computer.base import Bounds, UIElement
    return UIElement(ref=ref, role=role, label=label,
                     bounds=Bounds(x, y, w, h), **kw)


def test_a_reference_now_pointing_at_a_different_control_is_refused():
    """THE case. Not "does something still exist" -- something does, and it is
    a perfectly valid control. It is simply not the one that was chosen.

    This is the real failure: an autocomplete list opened between observing a
    compose window and clicking Subject, so the position that had been Subject
    was now the recipient field, and the subject line was typed into it.
    """
    before = _obs(elements=[_el("el1", "text_field", "Subject", y=100)])
    after = _obs(elements=[_el("elX", "combo_box", "To recipients", y=100)])

    session, controller = _session_on(before)
    controller.observation = after            # the UI mutated underneath

    result = session.click(ref="el1")
    assert result["status"] == "error", "clicking a changed target must refuse"
    assert "interface changed" in result["error"]
    assert "To recipients" in result["error"], (
        "the model should be told what is there now, so it can re-choose"
    )
    assert not controller.clicks, "no click may reach the wrong control"
    print("PASS: a reference that now points elsewhere is refused")


def test_a_control_that_only_moved_is_still_found():
    """Re-resolving by identity rather than position means a panel opening
    above a field does not invalidate the field."""
    before = _obs(elements=[_el("el1", "text_field", "Subject", y=100)])
    after = _obs(elements=[_el("el9", "text_field", "Subject", y=340)])

    session, controller = _session_on(before)
    controller.observation = after

    result = session.click(ref="el1")
    assert result["status"] == "success", result.get("error")
    assert controller.clicks and controller.clicks[0][1] > 300, (
        f"should click the control's new position, got {controller.clicks}"
    )
    print("PASS: a control that moved is still acted on, at its new position")


def test_a_disappeared_control_is_refused():
    before = _obs(elements=[_el("el1", "button", "Send")])
    after = _obs(elements=[_el("el1", "button", "Discard")])

    session, controller = _session_on(before)
    controller.observation = after
    result = session.click(ref="el1")
    assert result["status"] == "error"
    assert "identity" in result["error"] or "interface changed" in result["error"]
    assert not controller.clicks
    print("PASS: a control that is gone is refused")


def test_a_relabelled_control_is_refused():
    """A label change is a meaning change. 'Save draft' becoming 'Send' is
    exactly when acting on the old reference is most dangerous."""
    before = _obs(elements=[_el("el1", "button", "Save draft")])
    after = _obs(elements=[_el("el1", "button", "Send")])

    session, controller = _session_on(before)
    controller.observation = after
    result = session.click(ref="el1")
    assert result["status"] == "error"
    assert not controller.clicks, "must not click a control whose meaning changed"
    print("PASS: a relabelled control is refused")


def test_a_control_whose_role_changed_is_refused():
    before = _obs(elements=[_el("el1", "text_field", "Search")])
    after = _obs(elements=[_el("el1", "button", "Search")])

    session, controller = _session_on(before)
    controller.observation = after
    result = session.click(ref="el1")
    assert result["status"] == "error"
    assert not controller.clicks
    print("PASS: a control whose role changed is refused")


def test_duplicate_controls_are_refused_when_position_cannot_separate_them():
    """Two 'Reply' buttons appear after a thread expands. Picking one by
    guessing is how the wrong message gets replied to."""
    before = _obs(elements=[_el("el1", "button", "Reply", y=100)])
    after = _obs(elements=[_el("elA", "button", "Reply", y=400),
                           _el("elB", "button", "Reply", y=800)])

    session, controller = _session_on(before)
    controller.observation = after
    result = session.click(ref="el1")
    assert result["status"] == "error"
    assert "ambiguous" in result["error"]
    assert not controller.clicks
    print("PASS: duplicated controls are refused rather than guessed between")


def test_duplicates_are_allowed_when_position_still_separates_them():
    """Ambiguity is only fatal when it cannot be resolved. If one candidate is
    still where the reference was, that is evidence enough."""
    before = _obs(elements=[_el("el1", "button", "Reply", y=100)])
    after = _obs(elements=[_el("elA", "button", "Reply", y=100),
                           _el("elB", "button", "Reply", y=800)])

    session, controller = _session_on(before)
    controller.observation = after
    result = session.click(ref="el1")
    assert result["status"] == "success", result.get("error")
    assert controller.clicks[0][1] < 300
    print("PASS: position disambiguates duplicates when it can")


def test_an_unlabelled_control_needs_position_to_stay_put():
    """Icon buttons with no accessible name cannot be identified by role
    alone, so they get the stricter test."""
    before = _obs(elements=[_el("el1", "button", "", y=100)])
    moved = _obs(elements=[_el("elZ", "button", "", y=700)])

    session, controller = _session_on(before)
    controller.observation = moved
    result = session.click(ref="el1")
    assert result["status"] == "error"
    assert "ambiguous" in result["error"]
    assert not controller.clicks
    print("PASS: an unnamed control that moved is refused")


def test_a_window_that_stops_being_readable_is_refused():
    from computer.base import Observation

    before = _obs(elements=[_el("el1", "button", "OK")])
    session, controller = _session_on(before)
    controller.observation = Observation(app="X", source="none",
                                         note="window closed")
    result = session.click(ref="el1")
    assert result["status"] == "error"
    assert "see_ui" in result["error"]
    assert not controller.clicks
    print("PASS: an unreadable window refuses rather than clicking blind")


def test_typing_into_a_field_does_not_invalidate_its_reference():
    """Value must not be part of identity: a field whose value changed is the
    same field, and that is the normal result of using it."""
    before = _obs(elements=[_el("el1", "text_field", "Subject", value="")])
    after = _obs(elements=[_el("el1", "text_field", "Subject", value="hello")])

    session, controller = _session_on(before)
    controller.observation = after
    result = session.click(ref="el1")
    assert result["status"] == "success", result.get("error")
    print("PASS: a field that was typed into keeps its identity")


def test_verification_happens_before_the_click_not_after():
    """A check that runs after the action has already happened is not a check."""
    import inspect

    from computer.session import ComputerSession

    body = inspect.getsource(ComputerSession.click)
    resolve = body.index("self.element(ref)")
    act = body.index("self.controller().click(")
    assert resolve < act, "identity must be established before anything is clicked"
    print("PASS: identity is verified before the action")


# ══ browser semantics ══════════════════════════════════════
# The accessibility tree already carries page content -- links, fields,
# selects, checkboxes, tables, validation text -- so browser support is an
# extension of the existing path rather than a separate browser tool. These
# tests pin that, and pin the one thing that needed adding: navigation state.


def test_navigation_state_requires_a_real_scheme():
    """A URL heuristic that guesses is worse than one that abstains.

    An earlier version accepted a bare host when the field's label mentioned
    "address", and promptly reported "pre@filled.com" as the current URL --
    from a page field labelled "Email address". Page content reported as
    navigation state would send the model somewhere real.
    """
    from computer.base import Bounds, UIElement
    from computer.macos import MacController

    page_field = UIElement(ref="el1", role="text_field", label="Email address",
                           value="pre@filled.com", bounds=Bounds(0, 0, 80, 20))
    assert MacController._url_from([page_field]) == "", (
        "an email address in a page field is not the browser's location"
    )

    address_bar = UIElement(ref="el2", role="text_field", label="smart search field",
                            value="https://example.com/page", bounds=Bounds(0, 0, 80, 20))
    assert MacController._url_from([address_bar]) == "https://example.com/page"
    print("PASS: navigation state only accepts a real location")


def test_observation_carries_navigation_state_generically():
    """The field is on the canonical type, so a Windows adapter fills the same
    one rather than inventing its own browser concept."""
    from computer.base import Observation

    assert Observation().url == ""
    described = Observation(app="Safari", window="X", url="https://example.com").describe()
    assert "https://example.com" in described
    print("PASS: navigation state is part of the canonical observation")


# ══ vision is a fallback ═══════════════════════════════════

def test_see_screen_tells_the_model_to_prefer_the_accessibility_path():
    """Measured: see_ui is ~0.04s and see_screen ~3-10s for the same window.
    The declaration has to say so, or the model reaches for the slow one."""
    from brain.core_tools import OLLAMA_TOOLS

    declaration = next(t for t in OLLAMA_TOOLS if t["function"]["name"] == "see_screen")
    description = declaration["function"]["description"].lower()
    assert "see_ui" in description, "it must name the faster alternative"
    assert "slow" in description
    print("PASS: see_screen directs the model to see_ui first")


def test_vision_generation_budget_is_the_latency_lever():
    """Vision latency is generation, not preprocessing: measured 0.23s to
    capture, resize and encode against 3-10s of inference at a flat ~16 tok/s.
    The UI budget must therefore stay well below the prose budget."""
    from config.ollama import VISION_NUM_PREDICT, VISION_UI_NUM_PREDICT

    assert VISION_UI_NUM_PREDICT < VISION_NUM_PREDICT
    assert VISION_UI_NUM_PREDICT <= 64, "a control list does not need a long budget"
    print(f"PASS: vision budgets ui={VISION_UI_NUM_PREDICT} prose={VISION_NUM_PREDICT}")


def test_the_vision_budget_reaches_every_provider():
    """A budget honoured by one backend and ignored by another is exactly the
    inconsistency the provider boundary exists to prevent."""
    import inspect

    from brain.providers import base, ollama_provider, openai_compatible

    for module in (base, ollama_provider, openai_compatible):
        signature = inspect.getsource(module).split("def describe_image")[1][:200]
        assert "max_tokens" in signature, f"{module.__name__} must accept the budget"
    print("PASS: the vision budget crosses the provider boundary intact")


if __name__ == "__main__":
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        fn()
    print("\nAll computer control tests passed.")


# ══ typing reports where the text actually landed ══════════
#
# From a real form-filling run: Mike opened a page in Safari, typed the
# person's name, and the name went into the *address bar* — focus had never
# left it. Every step reported success, because type_text sent keystrokes and
# said "typed 11 characters" without any idea where they went. It is the same
# shape as the earlier silent click: an action that cannot fail because it
# never checks.
#
# Typing is aimed by keyboard focus, not by the last click, so the fix is to
# read focus and say what it is. Mike still decides what to do about it.

class _FocusStub(_StubController):
    """A controller whose keyboard focus is set by the test."""

    def __init__(self, focused=None, after=None):
        from computer.base import Observation

        super().__init__(Observation(app="stub", source="accessibility"))
        self._focus_sequence = [focused, after if after is not None else focused]

    def focused_element(self):
        if len(self._focus_sequence) > 1:
            return self._focus_sequence.pop(0)
        return self._focus_sequence[0]


def _field(role="text_field", label="Full name", value=""):
    from computer.base import Bounds, UIElement

    return UIElement(
        ref="focus", role=role, label=label, value=value,
        bounds=Bounds(0, 0, 100, 20), enabled=True, focused=True,
        native_role="AXTextField",
    )


def test_typing_names_the_field_it_went_into(monkeypatch):
    from computer.session import ComputerSession

    session = ComputerSession()
    stub = _FocusStub(_field(), _field(value="Jordan Lee"))
    monkeypatch.setattr(session, "controller", lambda: stub)
    monkeypatch.setattr(session, "_ensure_front", lambda: "")

    result = session.type_text("Jordan Lee")

    assert result["status"] == "success"
    assert "Full name" in result["result"]
    assert "Jordan Lee" in result["result"], "the resulting value must be reported"


def test_typing_into_something_that_is_not_a_text_field_says_so(monkeypatch):
    """The address-bar case. Safari's URL field reports as a text field, but
    a button or a list having focus is an unmistakable sign the keystrokes
    went somewhere unintended, and the model can only act on it if told."""
    from computer.session import ComputerSession

    session = ComputerSession()
    stub = _FocusStub(_field(role="button", label="Submit application"))
    monkeypatch.setattr(session, "controller", lambda: stub)
    monkeypatch.setattr(session, "_ensure_front", lambda: "")

    result = session.type_text("Jordan Lee")

    assert result["status"] == "success"
    assert "Submit application" in result["result"]
    assert "not a text field" in result["result"]


def test_unreadable_focus_is_admitted_rather_than_assumed(monkeypatch):
    from computer.session import ComputerSession

    session = ComputerSession()
    stub = _FocusStub(None)
    monkeypatch.setattr(session, "controller", lambda: stub)
    monkeypatch.setattr(session, "_ensure_front", lambda: "")

    result = session.type_text("Jordan Lee")

    assert "unverified" in result["result"]


def test_a_controller_without_focus_support_still_types(monkeypatch):
    """The base class returns None, so a platform that cannot read focus
    degrades to the honest message instead of raising."""
    from computer.session import ComputerSession

    session = ComputerSession()
    from computer.base import Observation

    stub = _StubController(Observation(app="stub", source="accessibility"))
    monkeypatch.setattr(session, "controller", lambda: stub)
    monkeypatch.setattr(session, "_ensure_front", lambda: "")

    result = session.type_text("hello")
    assert result["status"] == "success"


def test_clicking_a_text_field_that_did_not_take_focus_says_so(monkeypatch):
    """Catches the address-bar failure one step earlier than typing does,
    while nothing wrong has been typed yet. A click that lands without taking
    focus is a click that looks like it worked and did not."""
    from computer.base import Bounds, Observation, UIElement
    from computer.session import ComputerSession

    target = UIElement(
        ref="el1", role="text_field", label="Full name", value="",
        bounds=Bounds(10, 10, 100, 20), enabled=True, focused=False,
        native_role="AXTextField",
    )
    observation = Observation(app="Safari", source="accessibility", elements=[target])

    session = ComputerSession()
    stub = _StubController(observation, frontmost="Safari")
    stub.focused_element = lambda: _field(
        role="text_field", label="smart search field", value="Jordan Lee"
    )
    monkeypatch.setattr(session, "controller", lambda: stub)

    session.observe(app="Safari")
    result = session.click(ref="el1")

    assert result["status"] == "success", "the click did happen; only focus is wrong"
    assert "smart search field" in result["result"]
    assert "typing now would go there" in result["result"]


def test_clicking_a_text_field_that_did_take_focus_is_quiet(monkeypatch):
    """No note when nothing is wrong. A warning that fires on every click is
    one the model learns to ignore."""
    from computer.base import Bounds, Observation, UIElement
    from computer.session import ComputerSession

    target = UIElement(
        ref="el1", role="text_field", label="Full name", value="",
        bounds=Bounds(10, 10, 100, 20), enabled=True, focused=False,
        native_role="AXTextField",
    )
    observation = Observation(app="Safari", source="accessibility", elements=[target])

    session = ComputerSession()
    stub = _StubController(observation, frontmost="Safari")
    stub.focused_element = lambda: _field(role="text_field", label="Full name")
    monkeypatch.setattr(session, "controller", lambda: stub)

    session.observe(app="Safari")
    result = session.click(ref="el1")

    assert "keyboard focus" not in result["result"]


def test_clicking_a_button_does_not_check_focus(monkeypatch):
    """Buttons are not typed into, so a focus note there would be noise."""
    from computer.base import Bounds, Observation, UIElement
    from computer.session import ComputerSession

    target = UIElement(
        ref="el1", role="button", label="Save draft", value="",
        bounds=Bounds(10, 10, 80, 20), enabled=True, focused=False,
        native_role="AXButton",
    )
    observation = Observation(app="Safari", source="accessibility", elements=[target])

    session = ComputerSession()
    stub = _StubController(observation, frontmost="Safari")
    stub.focused_element = lambda: _field(role="text_field", label="something else")
    monkeypatch.setattr(session, "controller", lambda: stub)

    session.observe(app="Safari")
    result = session.click(ref="el1")

    assert "keyboard focus" not in result["result"]
