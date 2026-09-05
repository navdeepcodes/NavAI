"""Platform-independent computer interaction.

Mike already had file, terminal and browser-navigation tools. What it had no
way to do was operate an interface that exposes no API: click a control, type
into a field, switch windows. That is the gap this package fills.

Two rules shape everything here.

**Semantic before pixels.** Every desktop platform exposes an accessibility
tree — roles, titles, values, positions — as structured text. Reading that is
cheaper than a screenshot, more precise than pixel-hunting, and verifiable
afterwards. So the model asks for `observe()` and gets back a list of
addressable elements; it clicks `el_12`, not `(738, 412)`. Vision remains the
fallback for surfaces the accessibility tree cannot describe, which is what
makes this usable by a small local model at all.

**The runtime asks for an outcome, the adapter knows the API.** Nothing above
this file mentions CGEvent, AXUIElement, UIAutomation or XTest. The runtime
says "click this element"; the platform adapter decides how. macOS is
implemented; Windows is a defined interface with no body, deliberately, because
a fake implementation would be worse than an honest gap.
"""
from __future__ import annotations

import platform
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal


# ══ canonical types ════════════════════════════════════════

@dataclass
class Bounds:
    """Screen rectangle, in points, origin top-left."""

    x: int
    y: int
    width: int
    height: int

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)

    def describe(self) -> str:
        return f"{self.width}x{self.height} at ({self.x},{self.y})"


@dataclass
class UIElement:
    """One addressable control.

    `ref` is what the model uses to act on it. It is assigned per observation
    and is only valid for that observation — interfaces move, and pretending a
    reference survives a page change would produce confident clicks on the
    wrong thing.
    """

    ref: str
    role: str                      # normalised: button, text_field, link, ...
    label: str = ""                # title, description or nearest text
    value: str = ""                # current contents, for fields
    bounds: Bounds | None = None
    enabled: bool = True
    focused: bool = False
    native_role: str = ""          # the platform's own name, for debugging

    def identity(self) -> tuple:
        """What makes this the *same* control across observations.

        Deliberately excludes value and position. A field's value changes when
        it is typed into -- that is the point of typing into it -- and controls
        move when a page scrolls or a panel opens, neither of which makes them
        a different control. Role and accessible name are what a person uses
        to say "the Subject field", and they are what survives a re-render.

        Weak when a control has no name: many interfaces expose unlabelled
        icon buttons whose role alone cannot distinguish them. Callers must
        treat an empty label as insufficient on its own and fall back to
        position, or refuse.
        """
        return (self.role, (self.label or "").strip().casefold())

    @property
    def weakly_identified(self) -> bool:
        """True when role and name alone cannot pick this control out."""
        return not (self.label or "").strip()

    def describe(self) -> str:
        bits = [f"[{self.ref}]", self.role]
        if self.label:
            bits.append(repr(self.label[:60]))
        if self.value:
            bits.append(f"value={self.value[:40]!r}")
        if not self.enabled:
            bits.append("(disabled)")
        if self.focused:
            bits.append("(focused)")
        return " ".join(bits)


@dataclass
class WindowInfo:
    app: str
    title: str = ""
    bounds: Bounds | None = None
    window_id: int | None = None
    pid: int | None = None
    frontmost: bool = False

    def describe(self) -> str:
        where = f" {self.bounds.describe()}" if self.bounds else ""
        front = " (frontmost)" if self.frontmost else ""
        return f"{self.app}: {self.title or '(untitled)'}{where}{front}"


@dataclass
class Observation:
    """What Mike can currently tell about the screen.

    Deliberately compact. The whole point is that this is cheap enough to take
    before and after every action, on a local model, without flooding the
    context — so it carries what is needed to decide and to verify, and not a
    dump of the entire tree.
    """

    app: str = ""
    window: str = ""
    elements: list[UIElement] = field(default_factory=list)
    text: str = ""
    truncated: bool = False
    source: Literal["accessibility", "vision", "none"] = "none"
    note: str = ""
    # Where a browser is pointed, when the observed app is one. Platform
    # adapters fill this from whatever their browser exposes; nothing above
    # here knows how it was obtained. Empty for non-browser applications.
    url: str = ""

    def describe(self, limit: int = 40) -> str:
        head = f"{self.app} — {self.window or '(no window)'} [{self.source}]"
        lines = [head]
        if self.url:
            lines.append(f"  url: {self.url}")
        if self.note:
            lines.append(self.note)
        for element in self.elements[:limit]:
            lines.append("  " + element.describe())
        if len(self.elements) > limit:
            lines.append(f"  ... {len(self.elements) - limit} more elements")
        return "\n".join(lines)

    def find(self, ref: str) -> UIElement | None:
        return next((e for e in self.elements if e.ref == ref), None)

    def matching(self, identity: tuple) -> list[UIElement]:
        """Every control in this observation with the given identity."""
        return [e for e in self.elements if e.identity() == identity]


@dataclass
class ActionResult:
    """Every action says plainly whether it happened."""

    ok: bool
    detail: str = ""
    error: str = ""

    def as_dict(self) -> dict:
        if self.ok:
            return {"status": "success", "result": self.detail}
        return {"status": "error", "error": self.error or self.detail}


class ComputerError(Exception):
    """Raised for a platform failure the caller should report, not retry."""


# ══ roles ══════════════════════════════════════════════════
# Platform role vocabularies differ (AXButton vs Button vs push button). The
# model should not have to learn three of them, so adapters normalise into
# this set and keep the original in `native_role`.

ROLES = (
    "button", "text_field", "text_area", "link", "checkbox", "radio",
    "menu", "menu_item", "tab", "list", "list_item", "table", "row", "cell",
    "image", "text", "group", "window", "dialog", "slider", "combo_box",
    "scroll_area", "toolbar", "unknown",
)

# Labels that indicate an action a person cannot take back. Matched against the
# element's own label, so this is a property of the interface rather than a
# list of applications — the same rule protects a Send button in Gmail, Mail,
# Outlook or anything else that labels its controls honestly.
IRREVERSIBLE_LABELS = (
    "send", "submit", "delete", "remove", "discard", "trash", "erase",
    "buy", "purchase", "pay", "order", "checkout", "confirm order",
    "publish", "post", "share", "transfer", "withdraw", "deposit",
    "deactivate", "close account", "unsubscribe", "reset", "wipe",
    "empty trash", "move to trash", "permanently",
)


def looks_irreversible(label: str) -> str | None:
    """Return the matched phrase if this control looks like a point of no return.

    Deliberately conservative and deliberately imperfect: an unlabelled button
    cannot be judged this way, so this narrows the blast radius rather than
    eliminating it. The confirmation gate it feeds is the real protection.
    """
    text = (label or "").strip().lower()
    if not text:
        return None
    for phrase in IRREVERSIBLE_LABELS:
        if phrase == text or text.startswith(phrase + " ") or f" {phrase} " in f" {text} ":
            return phrase
    return None


# ══ the adapter interface ══════════════════════════════════

class ComputerController(ABC):
    """What every platform must provide.

    Kept small on purpose. These are primitives the model composes, not
    workflows — there is no `send_email()` here and there should never be one.
    """

    name: str = "unknown"

    # -- observation --------------------------------------------------
    @abstractmethod
    def observe(self, app: str | None = None, limit: int = 60) -> Observation:
        """Describe the focused window of `app`, or the frontmost window."""

    @abstractmethod
    def list_windows(self) -> list[WindowInfo]:
        """Every on-screen window Mike can address."""

    @abstractmethod
    def frontmost_app(self) -> str | None:
        ...

    # -- pointer ------------------------------------------------------
    @abstractmethod
    def click(self, x: int, y: int, button: str = "left", count: int = 1) -> ActionResult:
        ...

    @abstractmethod
    def scroll(self, dx: int, dy: int, x: int | None = None, y: int | None = None) -> ActionResult:
        ...

    @abstractmethod
    def drag(self, from_x: int, from_y: int, to_x: int, to_y: int) -> ActionResult:
        ...

    # -- keyboard -----------------------------------------------------
    def focused_element(self) -> UIElement | None:
        """Whatever currently has keyboard focus, or None if it cannot be read.

        Typing goes wherever focus is, which is not always where the last
        click landed. A platform that cannot answer this returns None and
        callers degrade to saying so, rather than to claiming the text went
        where it was aimed.
        """
        return None

    @abstractmethod
    def type_text(self, text: str) -> ActionResult:
        ...

    @abstractmethod
    def press_keys(self, key: str, modifiers: list[str] | None = None) -> ActionResult:
        ...

    # -- applications -------------------------------------------------
    @abstractmethod
    def activate_app(self, name: str) -> ActionResult:
        """Bring an already-running application to the front."""

    @abstractmethod
    def running_apps(self) -> list[str]:
        ...


def get_controller() -> ComputerController:
    """The adapter for this machine.

    Raises rather than returning a stub: a caller that cannot control the
    computer needs to know that now, not discover it from actions that
    silently do nothing.
    """
    system = platform.system()
    if system == "Darwin":
        from computer.macos import MacController

        return MacController()
    if system == "Windows":
        raise ComputerError(
            "Windows computer control is not implemented. The interface in "
            "computer/base.py defines what an implementation must provide; "
            "computer/macos.py is the reference. Nothing here is Mac-specific "
            "above the adapter boundary."
        )
    raise ComputerError(f"No computer control adapter for {system}.")
