"""The tool-facing surface of computer control.

`computer/base.py` defines what a platform must do and `computer/macos.py`
does it. This module is the thin layer between those and Mike's tools: it
holds the most recent observation so the model can say "click el7" instead of
"click (738, 412)", and it turns every action into the same result shape the
rest of the runtime uses.

Why references and not coordinates. A model that picks pixel coordinates from
a screenshot is guessing, and a guess that lands two pixels off clicks the
wrong control with total confidence. A reference is resolved against a real
element that was really on screen, with real bounds — and if the interface
moved in between, resolution fails loudly instead of clicking whatever is
there now.
"""
from __future__ import annotations

import logging
import time

from computer.base import (
    ComputerError,
    Observation,
    get_controller,
    looks_irreversible,
)

logger = logging.getLogger(__name__)

# Observations go stale as soon as the interface changes. This is long enough
# to observe, decide and act, and short enough that a reference from an
# earlier screen cannot be used against a later one.
REF_TTL_SECONDS = 120


class ComputerSession:
    """Holds the last observation so element references mean something."""

    def __init__(self) -> None:
        self._controller = None
        self._observation: Observation | None = None
        self._taken_at: float = 0.0
        self._app: str = ""
        self._last_limit: int = 60

    # -- lifecycle ----------------------------------------------------
    def controller(self):
        if self._controller is None:
            self._controller = get_controller()
        return self._controller

    def availability(self) -> tuple[bool, str]:
        try:
            controller = self.controller()
        except ComputerError as exc:
            return False, str(exc)
        checker = getattr(controller, "available", None)
        return checker() if checker else (True, "available")

    # -- observation --------------------------------------------------
    def observe(self, app: str | None = None, limit: int = 60) -> dict:
        self._last_limit = limit
        ok, why = self.availability()
        if not ok:
            return {"status": "error", "error": why}
        try:
            observation = self.controller().observe(app=app, limit=limit)
        except ComputerError as exc:
            return {"status": "error", "error": str(exc)}
        except Exception as exc:
            logger.exception("Observation failed")
            return {"status": "error", "error": f"Could not read the interface: {exc}"}

        # "I looked and the app is not there" is a failure, not an empty
        # success. Reporting it as success sent the model hunting for controls
        # on a screen that was never read, which costs steps and reads as the
        # interface being empty.
        if observation.source == "none":
            self._observation = None
            return {"status": "error",
                    "error": observation.note or "Nothing could be observed.",
                    "retry_safe": True}

        self._observation = observation
        self._taken_at = time.time()
        self._app = observation.app

        return {
            "status": "success",
            "app": observation.app,
            "window": observation.window,
            "source": observation.source,
            "element_count": len(observation.elements),
            "url": observation.url,
            "result": observation.describe(),
            "visible_text": observation.text[:800],
        }

    def element(self, ref: str, verify: bool = True):
        """Resolve a reference to the control it actually points at now.

        Age was the only check here, and age is not enough. A reference can be
        seconds old while the interface has changed underneath it: an
        autocomplete list opens, a panel re-renders, a row is inserted. The
        reference still resolves, to a *different* control, and the action
        lands somewhere the model never chose.

        That is not hypothetical. Measured on a real mail compose window: the
        subject text was typed into the recipient field because a dropdown
        appeared between observing and clicking, and the position that had been
        the Subject field was now something else.

        So a reference is re-resolved by identity at action time. The remembered
        element supplies role and accessible name; the interface is observed
        again; and the control carrying that identity *now* is what gets acted
        on -- which also means a control that merely moved is still found, at
        its new position.

        Refuses rather than guesses when identity cannot be established:
        nothing matches, or several things match and position cannot separate
        them. The caller is told to observe again, which is the only honest
        answer.
        """
        if self._observation is None:
            return None, (
                "No interface has been observed yet. Call see_ui first, then "
                "act on the references it returns."
            )
        if time.time() - self._taken_at > REF_TTL_SECONDS:
            return None, (
                f"That observation is over {REF_TTL_SECONDS}s old and the "
                "interface may have changed. Call see_ui again for current "
                "references."
            )
        remembered = self._observation.find(ref)
        if remembered is None:
            available = ", ".join(e.ref for e in self._observation.elements[:12])
            return None, (
                f"No element {ref!r} in the last observation of "
                f"{self._observation.app!r}. Available: {available}"
            )
        if remembered.bounds is None:
            return None, (
                f"Element {ref} ({remembered.role} {remembered.label!r}) has no "
                "screen position, so it cannot be clicked. It may be off-screen."
            )
        if not verify:
            return remembered, None

        return self._reresolve(ref, remembered)

    def _reresolve(self, ref: str, remembered):
        """Find the control carrying the remembered identity in the live UI."""
        try:
            fresh = self.controller().observe(app=self._app or None,
                                              limit=self._last_limit)
        except Exception as exc:
            logger.warning("Could not re-observe before acting: %s", exc)
            # Better to act on the remembered element than to block entirely
            # when observation itself is broken -- but say so.
            return remembered, None

        if fresh.source == "none":
            return None, (
                f"{self._app or 'The application'} is no longer showing a window "
                "that can be read. Call see_ui again."
            )

        identity = remembered.identity()
        candidates = fresh.matching(identity)

        if not candidates:
            near = self._describe_nearby(fresh, remembered)
            return None, (
                f"{ref} was {remembered.role} {remembered.label!r}, and nothing "
                f"with that identity is on screen now — the interface changed. "
                f"Call see_ui again and pick from the current controls.{near}"
            )

        if len(candidates) > 1 or remembered.weakly_identified:
            # Several controls share this identity, or it had no name to begin
            # with. Position is the only remaining evidence, and it is only
            # trustworthy if one candidate is still essentially where the
            # reference was.
            overlapping = [c for c in candidates
                           if c.bounds and self._overlaps(c.bounds, remembered.bounds)]
            if len(overlapping) == 1:
                return overlapping[0], None
            return None, (
                f"{ref} ({remembered.role} {remembered.label!r}) is ambiguous now: "
                f"{len(candidates)} controls share that identity and position "
                "does not separate them. Call see_ui again and choose explicitly."
            )

        resolved = candidates[0]
        if resolved.bounds is None:
            return None, (
                f"{ref} ({resolved.role} {resolved.label!r}) is present but has "
                "no screen position now."
            )
        return resolved, None

    @staticmethod
    def _overlaps(a, b) -> bool:
        """Whether two rectangles refer to plausibly the same place on screen."""
        if a is None or b is None:
            return False
        return not (a.x + a.width < b.x or b.x + b.width < a.x
                    or a.y + a.height < b.y or b.y + b.height < a.y)

    @staticmethod
    def _describe_nearby(fresh, remembered) -> str:
        """Name what is where the reference used to be, so the model can see
        what it would have clicked had the reference been trusted."""
        for element in fresh.elements:
            if element.bounds and ComputerSession._overlaps(element.bounds, remembered.bounds):
                return (f" A {element.role} {element.label!r} is now in that "
                        "position instead.")
        return ""

    def describe_element(self, ref: str) -> str:
        """What a reference points at, for confirmation prompts and logs."""
        if self._observation is None:
            return ref
        found = self._observation.find(ref)
        return found.describe() if found else ref

    def irreversible_target(self, ref: str) -> str | None:
        """The phrase that makes this element a point of no return, if any."""
        if self._observation is None:
            return None
        found = self._observation.find(ref)
        return looks_irreversible(found.label) if found else None

    # -- actions ------------------------------------------------------
    def _ensure_front(self) -> str:
        """Bring the observed application forward before acting on it.

        macOS does not deliver clicks to a window that is not frontmost --
        not even to raise it. Measured directly: with Safari behind another
        app, two clicks on a radio button at the correct screen coordinates
        changed nothing and did not bring Safari forward, while the click call
        reported success both times.

        That silent no-op is the worst kind of failure. The model did
        everything right -- observed the form, picked the correct element,
        clicked it -- and was told it had worked. An action therefore targets
        the application it was observed in, and focus is a precondition of
        the action rather than something the caller has to remember.

        Returns a note to append to the result when a switch was needed, so
        the change of focus is visible rather than hidden.
        """
        if not self._app:
            return ""
        try:
            controller = self.controller()
            current = controller.frontmost_app() or ""
            if current.lower() == self._app.lower():
                return ""
            result = controller.activate_app(self._app)
            # Wait for activation to actually complete rather than sleeping a
            # guessed interval. macOS consumes the click that activates a
            # window, so acting too early loses the action silently -- which
            # is the same failure this method exists to prevent, just moved
            # later. Measured: a fixed 0.35s was not enough and the first
            # click after a switch still vanished.
            deadline = time.time() + 2.5
            while time.time() < deadline:
                if (controller.frontmost_app() or "").lower() == self._app.lower():
                    time.sleep(0.55)     # let the window settle before acting
                    return f" (brought {self._app} to the front first)"
                time.sleep(0.1)
            if result.ok:
                return f" (brought {self._app} to the front first)"
            return f" (warning: could not bring {self._app} to the front: {result.error})"
        except Exception as exc:
            logger.warning("Could not raise %s before acting: %s", self._app, exc)
            return ""

    def click(self, ref: str | None = None, x: int | None = None,
              y: int | None = None, button: str = "left", count: int = 1) -> dict:
        ok, why = self.availability()
        if not ok:
            return {"status": "error", "error": why}

        # Focus first, then verify, then act. Raising the window can itself
        # change what is on screen -- an inactive window may re-render or a
        # panel may restore -- so identity has to be checked against the state
        # the click will actually meet, not the state before the switch.
        focus_note = self._ensure_front()

        target_note = ""
        if ref:
            element, problem = self.element(ref)
            if problem:
                return {"status": "error", "error": problem, "retry_safe": True}
            # A degenerate frame has no meaningful centre. VS Code reports its
            # editor as 0x14 at (254,224) -- zero pixels wide -- and clicking
            # "the middle" of that lands on a boundary, silently missing the
            # control. Refusing is better than a confident click on nothing.
            if element.bounds.width < 2 or element.bounds.height < 2:
                return {"status": "error", "error": (
                    f"{ref} ({element.role} {element.label!r}) reports an unusable "
                    f"screen area of {element.bounds.describe()}, so there is no "
                    "reliable point to click. It may already be focused — try "
                    "typing directly, or use see_screen to locate it visually."
                ), "retry_safe": True}
            x, y = element.bounds.center
            target_note = f" on {element.role} {element.label!r}"
            if not element.enabled:
                return {"status": "error", "error": (
                    f"{ref} ({element.label!r}) is disabled and cannot be clicked."
                )}
        elif x is None or y is None:
            return {"status": "error", "error": (
                "Give either a ref from see_ui, or both x and y. A ref is "
                "preferred: it is checked against a real element."
            )}

        result = self.controller().click(int(x), int(y), button=button, count=count)
        if not result.ok:
            return {"status": "error", "error": result.error or result.detail}

        # Clicking a text field is nearly always a prelude to typing into it,
        # and a click that lands without taking focus sends the next
        # keystrokes somewhere else entirely -- measured, into a browser's
        # address bar. Checking here catches it one step earlier than the
        # typing does, while nothing wrong has been typed yet.
        focus_check = ""
        if ref and element is not None and element.role in self._TEXT_ROLES:
            focused = self._focused()
            if focused is None:
                focus_check = " (whether it took keyboard focus could not be read)"
            elif focused.identity() != element.identity():
                landed = (f"{focused.role} {focused.label!r}"
                          if focused.label else focused.role)
                focus_check = (
                    f" — but keyboard focus is on {landed}, not on this control, "
                    "so typing now would go there instead. Click it again or "
                    "check the interface before typing."
                )

        return {
            "status": "success",
            "result": result.detail + target_note + focus_check + focus_note,
        }

    # Roles that accept typed text. Anything else having focus means the
    # keystrokes are going somewhere the caller probably did not intend.
    _TEXT_ROLES = frozenset({"text_field", "text_area", "combo_box"})

    def type_text(self, text: str) -> dict:
        ok, why = self.availability()
        if not ok:
            return {"status": "error", "error": why}
        # Keystrokes go to whatever is frontmost, so the same precondition
        # applies: type into the application that was observed, not whatever
        # happens to be in front now.
        note = self._ensure_front()

        # Where the text is about to go. Typing is aimed by focus, not by the
        # last click, and the two are not always the same control -- measured:
        # a form-filling run typed a person's name into Safari's address bar
        # while every step reported success, because nothing ever said which
        # control had focus. Reading it costs one accessibility call.
        before = self._focused()

        result = self.controller().type_text(text).as_dict()
        if result.get("status") != "success":
            return result

        after = self._focused()
        landed = after or before

        if landed is None:
            result["result"] = (
                result.get("result", "")
                + " — but the focused control could not be read, so where the "
                "text went is unverified. Use see_ui to check."
            ) + note
            return result

        where = f"{landed.role} {landed.label!r}" if landed.label else landed.role
        detail = f" into {where}"
        if landed.value:
            detail += f", which now reads {landed.value[:120]!r}"
        if landed.role not in self._TEXT_ROLES:
            detail += (
                f" — note that {landed.role} is not a text field, so the "
                "keystrokes may not have gone where you intended"
            )
        result["result"] = result.get("result", "") + detail + note
        result["focused"] = where
        return result

    def _focused(self):
        """The control holding keyboard focus, or None if unreadable."""
        try:
            return self.controller().focused_element()
        except Exception:
            return None

    def press_keys(self, key: str, modifiers: list[str] | None = None) -> dict:
        ok, why = self.availability()
        if not ok:
            return {"status": "error", "error": why}
        note = self._ensure_front()
        result = self.controller().press_keys(key, modifiers).as_dict()
        if note and result.get("status") == "success":
            result["result"] = result.get("result", "") + note
        return result

    def scroll(self, dy: int = 0, dx: int = 0, ref: str | None = None) -> dict:
        ok, why = self.availability()
        if not ok:
            return {"status": "error", "error": why}
        x = y = None
        if ref:
            element, problem = self.element(ref)
            if problem:
                return {"status": "error", "error": problem, "retry_safe": True}
            x, y = element.bounds.center
        return self.controller().scroll(dx, dy, x, y).as_dict()

    def list_windows(self) -> dict:
        ok, why = self.availability()
        if not ok:
            return {"status": "error", "error": why}
        windows = self.controller().list_windows()
        if not windows:
            return {"status": "success", "result": "No addressable windows are open."}
        return {
            "status": "success",
            "count": len(windows),
            "result": "\n".join(w.describe() for w in windows[:25]),
        }

    def focus_app(self, name: str) -> dict:
        ok, why = self.availability()
        if not ok:
            return {"status": "error", "error": why}
        result = self.controller().activate_app(name)
        if result.ok:
            # The previous observation belongs to the previous app.
            self._observation = None
            self._app = name
        return result.as_dict()


# One session per process. The observation it holds is short-lived state about
# the screen, not user data, so it is deliberately not persisted.
SESSION = ComputerSession()
