"""macOS implementation of ComputerController.

Everything platform-specific about operating this machine lives here:
AXUIElement for reading interfaces, CGEvent for driving them, NSWorkspace for
applications. Nothing above `computer/base.py` imports any of it.

Permissions this needs, and what happens without them:

  Accessibility     required. Without it the AX tree is empty and synthetic
                    events are dropped silently, so `available()` checks it up
                    front and says so rather than letting actions no-op.
  Screen Recording  only for window *titles* in the window list. Absent, the
                    list still enumerates windows but titles come back blank.

Granting is per responsible process: a terminal-launched run inherits the
terminal's grant, and a packaged Mike.app needs its own.
"""
from __future__ import annotations

import subprocess
import time

from AppKit import NSWorkspace
from ApplicationServices import (
    AXIsProcessTrusted,
    AXUIElementCopyAttributeValue,
    AXUIElementCreateApplication,
    AXUIElementSetAttributeValue,
    AXUIElementPerformAction,
    AXValueGetValue,
    kAXChildrenAttribute,
    kAXDescriptionAttribute,
    kAXEnabledAttribute,
    kAXFocusedAttribute,
    kAXFocusedWindowAttribute,
    kAXFocusedUIElementAttribute,
    kAXParentAttribute,
    kAXMainWindowAttribute,
    kAXMainAttribute,
    kAXRaiseAction,
    kAXPositionAttribute,
    kAXRoleAttribute,
    kAXSizeAttribute,
    kAXTitleAttribute,
    kAXValueAttribute,
    kAXValueCGPointType,
    kAXValueCGSizeType,
    kAXWindowsAttribute,
)
import Quartz

_MAX_DEPTH = 60      # deep enough for nested web content
_MAX_NODES = 20000   # bounds a pathological tree without truncating real ones

# Rows and cells describe content rather than offering an action. They are
# still worth reporting -- reading a table is a real task -- but they must not
# consume the observation budget that buttons and fields need.
_BULK_ROLES = {"row", "cell"}
_BULK_BUDGET = 30

# A focused region should be a panel: big enough to be a dialog, small enough
# not to be the whole page.
_FOCUS_CLIMB_LIMIT = 12
_FOCUS_REGION_MIN = 6
_FOCUS_REGION_MAX = 80

from computer.base import (
    ActionResult,
    Bounds,
    ComputerController,
    ComputerError,
    Observation,
    UIElement,
    WindowInfo,
)

# ── role translation ──────────────────────────────────────
# The model should not have to learn Apple's vocabulary.
_ROLE_MAP = {
    "AXButton": "button", "AXPopUpButton": "combo_box", "AXMenuButton": "button",
    "AXTextField": "text_field", "AXSecureTextField": "text_field",
    "AXTextArea": "text_area", "AXLink": "link", "AXCheckBox": "checkbox",
    "AXRadioButton": "radio", "AXMenu": "menu", "AXMenuItem": "menu_item",
    "AXMenuBarItem": "menu_item", "AXTabGroup": "tab", "AXList": "list",
    "AXTable": "table", "AXRow": "row", "AXCell": "cell", "AXImage": "image",
    "AXStaticText": "text", "AXGroup": "group", "AXWindow": "window",
    "AXSheet": "dialog", "AXDialog": "dialog", "AXSlider": "slider",
    "AXComboBox": "combo_box", "AXScrollArea": "scroll_area",
    "AXToolbar": "toolbar", "AXWebArea": "group", "AXHeading": "text",
}

# Roles worth showing the model. A tree is mostly nesting scaffolding; listing
# every AXGroup buries the handful of things that can actually be acted on.
_ACTIONABLE = {
    "button", "text_field", "text_area", "link", "checkbox", "radio",
    "menu_item", "tab", "combo_box", "slider", "row", "cell",
}

# Keys addressable by name. Printable characters go through type_text, which
# handles any unicode, so this only covers what has no character.
_KEYS = {
    "return": 0x24, "enter": 0x24, "tab": 0x30, "space": 0x31,
    "delete": 0x33, "backspace": 0x33, "forward_delete": 0x75,
    "escape": 0x35, "esc": 0x35, "home": 0x73, "end": 0x77,
    "page_up": 0x74, "page_down": 0x79,
    "left": 0x7B, "right": 0x7C, "down": 0x7D, "up": 0x7E,
    "f1": 0x7A, "f2": 0x78, "f3": 0x63, "f4": 0x76, "f5": 0x60,
    "f6": 0x61, "f7": 0x62, "f8": 0x64, "f9": 0x65, "f10": 0x6D,
    "f11": 0x67, "f12": 0x6F,
    "a": 0x00, "b": 0x0B, "c": 0x08, "d": 0x02, "e": 0x0E, "f": 0x03,
    "g": 0x05, "h": 0x04, "i": 0x22, "j": 0x26, "k": 0x28, "l": 0x25,
    "m": 0x2E, "n": 0x2D, "o": 0x1F, "p": 0x23, "q": 0x0C, "r": 0x0F,
    "s": 0x01, "t": 0x11, "u": 0x20, "v": 0x09, "w": 0x0D, "x": 0x07,
    "y": 0x10, "z": 0x06,
    "0": 0x1D, "1": 0x12, "2": 0x13, "3": 0x14, "4": 0x15,
    "5": 0x17, "6": 0x16, "7": 0x1A, "8": 0x1C, "9": 0x19,
}

_MODIFIERS = {
    "cmd": Quartz.kCGEventFlagMaskCommand, "command": Quartz.kCGEventFlagMaskCommand,
    "shift": Quartz.kCGEventFlagMaskShift,
    "alt": Quartz.kCGEventFlagMaskAlternate, "option": Quartz.kCGEventFlagMaskAlternate,
    "ctrl": Quartz.kCGEventFlagMaskControl, "control": Quartz.kCGEventFlagMaskControl,
    "fn": Quartz.kCGEventFlagMaskSecondaryFn,
}


def _attr(element, attribute):
    """One accessibility attribute, or None. AX calls fail routinely — an
    element can vanish between being listed and being read — so this never
    raises."""
    try:
        err, value = AXUIElementCopyAttributeValue(element, attribute, None)
        return value if err == 0 else None
    except Exception:
        return None


def _geometry(element) -> Bounds | None:
    position, size = _attr(element, kAXPositionAttribute), _attr(element, kAXSizeAttribute)
    if position is None or size is None:
        return None
    try:
        ok_p, point = AXValueGetValue(position, kAXValueCGPointType, None)
        ok_s, extent = AXValueGetValue(size, kAXValueCGSizeType, None)
        if not (ok_p and ok_s):
            return None
        return Bounds(int(point.x), int(point.y), int(extent.width), int(extent.height))
    except Exception:
        return None


class MacController(ComputerController):
    name = "macos"

    # -- availability -------------------------------------------------
    @staticmethod
    def available() -> tuple[bool, str]:
        """Whether control will actually work, checked rather than assumed.

        Synthetic events are dropped silently without Accessibility, which
        would otherwise look like a model that clicked the wrong place.
        """
        if not AXIsProcessTrusted():
            return False, (
                "macOS Accessibility permission is not granted for this process, "
                "so Mike cannot read interfaces or send clicks and keystrokes. "
                "Grant it in System Settings > Privacy & Security > Accessibility "
                "for the application running Mike, then try again."
            )
        return True, "accessibility granted"

    def _require(self) -> None:
        ok, why = self.available()
        if not ok:
            raise ComputerError(why)

    # -- observation --------------------------------------------------
    def frontmost_app(self) -> str | None:
        """Which application is actually in front.

        Read from the CoreGraphics window list rather than
        NSWorkspace.frontmostApplication(). NSWorkspace answers from a cache
        that is refreshed by run-loop notifications, and Mike's tool calls
        happen without one -- so it returns whatever was frontmost when the
        process started and never updates. Measured directly: after switching
        apps three times, NSWorkspace still named the first app every time
        while the window list tracked each change.
        """
        options = (Quartz.kCGWindowListOptionOnScreenOnly
                   | Quartz.kCGWindowListExcludeDesktopElements)
        for entry in Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID) or []:
            if entry.get("kCGWindowLayer", 0) != 0:      # skip menu bar, dock, overlays
                continue
            box = entry.get("kCGWindowBounds") or {}
            if int(box.get("Width", 0)) * int(box.get("Height", 0)) < 20000:
                continue
            owner = entry.get("kCGWindowOwnerName")
            if owner:
                return owner
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        return app.localizedName() if app else None

    def _app_by_name(self, name: str):
        """Find a running app by the name a person would use.

        Matching has to work in both directions. macOS reports VS Code as
        "Code", so asking for "Visual Studio Code" found nothing with a plain
        `wanted in actual` test -- the requested name was the longer one. The
        bundle identifier is checked too, since that is where the full name
        usually survives.
        """
        wanted = (name or "").strip().lower()
        if not wanted:
            return None

        candidates = [a for a in NSWorkspace.sharedWorkspace().runningApplications()
                      if a.activationPolicy() == 0]

        for app in candidates:
            if (app.localizedName() or "").lower() == wanted:
                return app

        for app in candidates:
            actual = (app.localizedName() or "").lower()
            bundle = (app.bundleIdentifier() or "").lower()
            if not actual:
                continue
            if wanted in actual or actual in wanted or wanted.replace(" ", "") in bundle:
                return app
        return None

    def observe(self, app: str | None = None, limit: int = 60) -> Observation:
        self._require()

        target = self._app_by_name(app) if app else NSWorkspace.sharedWorkspace().frontmostApplication()
        if target is None:
            return Observation(
                app=app or "", source="none",
                note=f"No running application named {app!r}. Use list_windows to see what is open.",
            )

        app_name = target.localizedName() or ""
        ax_app = AXUIElementCreateApplication(target.processIdentifier())
        self._enable_manual_accessibility(ax_app)
        window = self._best_window(ax_app)
        if window is None:
            return Observation(
                app=app_name, source="none",
                note=f"{app_name} is running but has no accessible window.",
            )

        elements: list[UIElement] = []
        text_bits: list[str] = []
        counter = [0, 0, 0]

        # Describe whatever has keyboard focus first.
        #
        # A window is not a flat list of equally interesting controls. When a
        # dialog, panel or compose window is open, that is where the work is
        # happening -- and it is usually last in tree order, behind everything
        # already on the page. Observing in tree order on a mail inbox spent
        # the entire budget on message rows and never reached the compose
        # window sitting on top of them: no To field, no Subject, no Send
        # button, all plainly visible on screen.
        #
        # Focus is the interface telling us which region matters. This is a
        # property of interfaces in general, not of any one application.
        focused_region = self._focused_region(ax_app, window)
        if focused_region is not None:
            self._walk(focused_region, elements, text_bits, counter, limit)

        seen = {(e.role, e.label, e.bounds.describe() if e.bounds else None) for e in elements}
        rest: list[UIElement] = []
        truncated = self._walk(window, rest, text_bits, counter, limit)
        for element in rest:
            key = (element.role, element.label, element.bounds.describe() if element.bounds else None)
            if key not in seen:
                seen.add(key)
                elements.append(element)
        # References are handed out in walk order, so renumber once the final
        # ordering is known. A reference the caller cannot resolve is worse
        # than no reference.
        for index, element in enumerate(elements[:limit], start=1):
            element.ref = f"el{index}"
        elements = elements[:limit]

        return Observation(
            app=app_name,
            window=str(_attr(window, kAXTitleAttribute) or ""),
            elements=elements,
            text=" ".join(text_bits[:120])[:2000],
            truncated=truncated,
            source="accessibility",
            url=self._url_from(elements),
        )

    @staticmethod
    def _url_from(elements) -> str:
        """The address a browser is showing, if this is a browser.

        Browsers put it in an ordinary text field in their own toolbar --
        Safari calls it "smart search field", others name it differently.
        Rather than teaching the model each browser's vocabulary, the address
        is lifted out here and reported as navigation state, which is what it
        actually is.

        Only a value carrying a scheme counts. An earlier version also
        accepted a bare host when the field's label mentioned "address", and
        immediately reported "pre@filled.com" as the current URL -- the page
        had a field labelled "Email address". Reporting page content as
        navigation state is worse than reporting nothing, so the loose branch
        is gone. A browser showing a bare host simply yields no URL here.
        """
        for element in elements:
            if element.role != "text_field" or not element.value:
                continue
            value = element.value.strip()
            if value.startswith(("http://", "https://", "file://", "about:")):
                return value
        return ""

    @staticmethod
    def _enable_manual_accessibility(ax_app) -> None:
        """Ask a Chromium-based app to build its accessibility tree.

        Chromium keeps the tree off until an assistive client asks, and exposes
        AXManualAccessibility as the documented opt-in. Setting it is harmless
        for apps that ignore it and is not specific to any one application.

        Honest note: this was NOT what made Electron apps readable here. The
        Claude desktop app already served a full tree and reported this
        attribute as False afterwards -- the real defect was window selection
        below. This stays because it is the correct request to make for apps
        that genuinely do gate on it, not because it was the fix.
        """
        try:
            AXUIElementSetAttributeValue(ax_app, "AXManualAccessibility", True)
        except Exception:
            pass

    def _best_window(self, ax_app):
        """Pick the window that actually holds the interface.

        Asking only for the focused window fails whenever the target app is
        not frontmost, and falling back to windows[0] is worse than useless in
        Electron: those apps carry an untitled zero-child helper window in that
        slot, so observation returned "no elements" for an app whose tree was
        fully populated one window along. Prefer focused, then main, then the
        first window with actual content.
        """
        for attribute in (kAXFocusedWindowAttribute, kAXMainWindowAttribute):
            window = _attr(ax_app, attribute)
            if window is not None and (_attr(window, kAXChildrenAttribute) or []):
                return window

        windows = _attr(ax_app, kAXWindowsAttribute) or []
        # A window with children beats one without; a titled window beats an
        # untitled one. Both rules exist because Electron violates the naive
        # assumption that windows[0] is the real one.
        scored = []
        for window in windows:
            children = len(_attr(window, kAXChildrenAttribute) or [])
            titled = 1 if str(_attr(window, kAXTitleAttribute) or "") else 0
            scored.append((children > 0, titled, children, window))
        scored.sort(key=lambda row: (row[0], row[1], row[2]), reverse=True)
        if scored and scored[0][0]:
            return scored[0][3]

        for attribute in (kAXFocusedWindowAttribute, kAXMainWindowAttribute):
            window = _attr(ax_app, attribute)
            if window is not None:
                return window
        return windows[0] if windows else None

    def focused_element(self) -> UIElement | None:
        """The control that will receive the next keystroke."""
        app = self.frontmost_app()
        if not app:
            return None
        target = self._app_by_name(app)
        if target is None:
            return None
        try:
            ax_app = AXUIElementCreateApplication(target.processIdentifier())
        except Exception:
            return None

        node = _attr(ax_app, kAXFocusedUIElementAttribute)
        if node is None:
            return None

        native = str(_attr(node, kAXRoleAttribute) or "")
        label = _attr(node, kAXTitleAttribute) or _attr(node, kAXDescriptionAttribute) or ""
        value = _attr(node, kAXValueAttribute)
        return UIElement(
            ref="focus",
            role=_ROLE_MAP.get(native, "unknown"),
            label=str(label)[:120],
            value=str(value)[:200] if isinstance(value, (str, int, float)) else "",
            bounds=_geometry(node),
            enabled=bool(_attr(node, kAXEnabledAttribute) is not False),
            focused=True,
            native_role=native,
        )

    def _focused_region(self, ax_app, window):
        """The panel around whatever currently has keyboard focus.

        Climbing a fixed number of levels does not work: web interfaces wrap
        a control in several single-child groups before reaching anything
        meaningful, and one level too far jumps straight from a dialog to the
        entire page. Measured on an open mail compose window, ancestors held
        1, 1, 4, 5, 18, 21 actionable controls -- and then 377.

        So the climb is bounded by size rather than by depth: keep going while
        the region is still smaller than a page, and keep the largest one that
        is still a panel. That yields the compose window rather than either the
        single field inside it or the inbox behind it.
        """
        focused = _attr(ax_app, kAXFocusedUIElementAttribute)
        if focused is None:
            return None

        best = None
        node = focused
        for _ in range(_FOCUS_CLIMB_LIMIT):
            parent = _attr(node, kAXParentAttribute)
            if parent is None:
                break
            node = parent
            size = self._actionable_count(node)
            if size > _FOCUS_REGION_MAX:
                break
            if size >= _FOCUS_REGION_MIN:
                best = node
        return best

    @staticmethod
    def _actionable_count(node, depth=0, budget=None) -> int:
        """How many things in this subtree can be acted on. Bounded: this runs
        once per ancestor and only needs to distinguish 'panel' from 'page'."""
        if budget is None:
            budget = [_FOCUS_REGION_MAX * 3]
        if depth > 25 or budget[0] <= 0:
            return 0
        budget[0] -= 1
        total = 1 if _ROLE_MAP.get(str(_attr(node, kAXRoleAttribute) or "")) in _ACTIONABLE else 0
        for child in (_attr(node, kAXChildrenAttribute) or [])[:40]:
            total += MacController._actionable_count(child, depth + 1, budget)
        return total

    def _walk(self, node, out, text_bits, counter, limit, depth=0) -> bool:
        """Collect actionable elements breadth-first-ish, capped.

        Depth is capped because web content nests arbitrarily deep and an
        uncapped walk on a browser window takes seconds and returns thousands
        of groups — useless to a model with a 40k context and slow besides.
        """
        if len(out) >= limit or depth > _MAX_DEPTH:
            return len(out) >= limit
        # A node budget rather than a shallow depth cap: web content nests
        # arbitrarily deep, so depth alone either truncates real controls or
        # lets a pathological tree run for seconds. This bounds the work
        # without hiding elements that are merely deep.
        counter[1] += 1
        if counter[1] > _MAX_NODES:
            return True

        native = str(_attr(node, kAXRoleAttribute) or "")
        role = _ROLE_MAP.get(native, "unknown")
        label = _attr(node, kAXTitleAttribute) or _attr(node, kAXDescriptionAttribute) or ""
        value = _attr(node, kAXValueAttribute)

        if role == "text" and isinstance(value, str) and value.strip():
            text_bits.append(value.strip())
        elif role == "text" and isinstance(label, str) and label.strip():
            text_bits.append(label.strip())

        if role in _ACTIONABLE:
            # Bulk content must not crowd out controls. A mail inbox, a long
            # table or any list view produces hundreds of rows and cells, and
            # collecting them in tree order filled the entire budget before
            # the walk ever reached the compose window sitting on top of the
            # page -- the observation reported no text fields and no Send
            # button while both were plainly on screen.
            #
            # Rows and cells are content, not primary controls, so they get a
            # small fixed share and everything else keeps the rest. This is a
            # statement about interfaces in general, not about any one
            # application.
            if role in _BULK_ROLES:
                if counter[2] >= _BULK_BUDGET:
                    for child in (_attr(node, kAXChildrenAttribute) or []):
                        if self._walk(child, out, text_bits, counter, limit, depth + 1):
                            return True
                    return len(out) >= limit
                counter[2] += 1

            counter[0] += 1
            out.append(UIElement(
                ref=f"el{counter[0]}",
                role=role,
                label=str(label)[:120],
                value=str(value)[:120] if isinstance(value, (str, int, float)) else "",
                bounds=_geometry(node),
                enabled=bool(_attr(node, kAXEnabledAttribute) is not False),
                focused=bool(_attr(node, kAXFocusedAttribute)),
                native_role=native,
            ))

        for child in (_attr(node, kAXChildrenAttribute) or []):
            if self._walk(child, out, text_bits, counter, limit, depth + 1):
                return True
        return len(out) >= limit

    def list_windows(self) -> list[WindowInfo]:
        front = self.frontmost_app()
        options = (Quartz.kCGWindowListOptionOnScreenOnly
                   | Quartz.kCGWindowListExcludeDesktopElements)
        found: list[WindowInfo] = []
        for entry in Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID) or []:
            owner = entry.get("kCGWindowOwnerName") or ""
            if not owner:
                continue
            box = entry.get("kCGWindowBounds") or {}
            # Menu-bar extras and status items are "windows" to CoreGraphics --
            # roughly forty pixels tall, pinned to the top strip. Listing them
            # buries the handful of real windows a person would call a window,
            # so they are dropped rather than ranked down.
            if box and int(box.get("Height", 0)) <= 50 and int(box.get("Y", 0)) <= 40:
                continue
            if box and int(box.get("Width", 0)) * int(box.get("Height", 0)) < 20000:
                continue
            found.append(WindowInfo(
                app=owner,
                title=entry.get("kCGWindowName") or "",
                bounds=Bounds(int(box.get("X", 0)), int(box.get("Y", 0)),
                              int(box.get("Width", 0)), int(box.get("Height", 0))) if box else None,
                window_id=entry.get("kCGWindowNumber"),
                pid=entry.get("kCGWindowOwnerPID"),
                frontmost=(owner == front),
            ))
        # Frontmost first: it is what an instruction like "this window" means.
        found.sort(key=lambda w: (not w.frontmost, w.app.lower()))
        return found

    def running_apps(self) -> list[str]:
        return sorted(
            (a.localizedName() or "") for a in NSWorkspace.sharedWorkspace().runningApplications()
            if a.activationPolicy() == 0 and a.localizedName()
        )

    # -- pointer ------------------------------------------------------
    def click(self, x: int, y: int, button: str = "left", count: int = 1) -> ActionResult:
        self._require()
        down, up, btn = {
            "left": (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp, Quartz.kCGMouseButtonLeft),
            "right": (Quartz.kCGEventRightMouseDown, Quartz.kCGEventRightMouseUp, Quartz.kCGMouseButtonRight),
        }.get(button, (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp, Quartz.kCGMouseButtonLeft))

        point = Quartz.CGPointMake(x, y)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap,
                           Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, point, btn))
        time.sleep(0.02)
        for index in range(1, count + 1):
            for kind in (down, up):
                event = Quartz.CGEventCreateMouseEvent(None, kind, point, btn)
                # Without this a double-click reads as two unrelated clicks.
                Quartz.CGEventSetIntegerValueField(event, Quartz.kCGMouseEventClickState, index)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
            time.sleep(0.03)
        label = {1: "click", 2: "double-click", 3: "triple-click"}.get(count, f"{count}x click")
        return ActionResult(True, f"{button} {label} at ({x}, {y})")

    def scroll(self, dx: int, dy: int, x: int | None = None, y: int | None = None) -> ActionResult:
        self._require()
        if x is not None and y is not None:
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, Quartz.CGEventCreateMouseEvent(
                None, Quartz.kCGEventMouseMoved, Quartz.CGPointMake(x, y), Quartz.kCGMouseButtonLeft))
            time.sleep(0.02)
        event = Quartz.CGEventCreateScrollWheelEvent(None, Quartz.kCGScrollEventUnitPixel, 2, dy, dx)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        return ActionResult(True, f"scrolled dx={dx} dy={dy}")

    def drag(self, from_x: int, from_y: int, to_x: int, to_y: int) -> ActionResult:
        self._require()
        btn = Quartz.kCGMouseButtonLeft
        start, end = Quartz.CGPointMake(from_x, from_y), Quartz.CGPointMake(to_x, to_y)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap,
                           Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, start, btn))
        time.sleep(0.03)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap,
                           Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown, start, btn))
        # Interpolated: a single jump is ignored by most drag targets.
        steps = 12
        for i in range(1, steps + 1):
            point = Quartz.CGPointMake(
                from_x + (to_x - from_x) * i / steps,
                from_y + (to_y - from_y) * i / steps,
            )
            Quartz.CGEventPost(Quartz.kCGHIDEventTap,
                               Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDragged, point, btn))
            time.sleep(0.012)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap,
                           Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseUp, end, btn))
        return ActionResult(True, f"dragged ({from_x},{from_y}) -> ({to_x},{to_y})")

    # -- keyboard -----------------------------------------------------
    def type_text(self, text: str) -> ActionResult:
        self._require()
        if not text:
            return ActionResult(False, error="No text given to type.")
        # Unicode strings rather than keycodes: this types accents, emoji and
        # non-Latin scripts without a per-layout keycode table.
        for chunk_start in range(0, len(text), 20):
            chunk = text[chunk_start:chunk_start + 20]
            for kind in (True, False):
                event = Quartz.CGEventCreateKeyboardEvent(None, 0, kind)
                Quartz.CGEventKeyboardSetUnicodeString(event, len(chunk), chunk)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
            time.sleep(0.01)
        return ActionResult(True, f"typed {len(text)} characters")

    def press_keys(self, key: str, modifiers: list[str] | None = None) -> ActionResult:
        self._require()
        code = _KEYS.get((key or "").strip().lower())
        if code is None:
            return ActionResult(False, error=(
                f"Unknown key {key!r}. Named keys: {', '.join(sorted(_KEYS)[:14])}... "
                "For ordinary characters use type_text instead."
            ))
        flags = 0
        for modifier in (modifiers or []):
            mask = _MODIFIERS.get(modifier.strip().lower())
            if mask is None:
                return ActionResult(False, error=(
                    f"Unknown modifier {modifier!r}. Use: cmd, shift, alt, ctrl, fn."
                ))
            flags |= mask
        for is_down in (True, False):
            event = Quartz.CGEventCreateKeyboardEvent(None, code, is_down)
            if flags:
                Quartz.CGEventSetFlags(event, flags)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
            time.sleep(0.01)
        combo = "+".join((modifiers or []) + [key])
        return ActionResult(True, f"pressed {combo}")

    # -- applications -------------------------------------------------
    def activate_app(self, name: str) -> ActionResult:
        self._require()
        app = self._app_by_name(name)
        if app is None:
            return ActionResult(False, error=(
                f"No running application named {name!r}. Open it first with "
                f"open_application, or check list_windows for what is running."
            ))
        # Modern macOS refuses cross-application activation from a process
        # that is not itself frontmost, so activateWithOptions_ returns without
        # doing anything -- measured: the target's isActive stayed False and
        # the front app never changed. LaunchServices ("open -a") is not
        # subject to that restriction and needs no extra permission, so it is
        # the primary path and the Cocoa call remains as a cheap first try.
        app.activateWithOptions_(1 << 1)   # NSApplicationActivateIgnoringOtherApps
        time.sleep(0.25)
        if (self.frontmost_app() or "").lower() != (app.localizedName() or "").lower():
            try:
                subprocess.run(["open", "-a", app.localizedName() or name],
                               capture_output=True, timeout=10)
                time.sleep(0.6)
            except Exception:
                pass

        # Activating an application is not the same as giving one of its
        # windows keyboard focus. An app can be frontmost with no key window,
        # and then synthetic keystrokes go nowhere while every check still
        # reports success -- which is exactly how this failed: focus_app said
        # "now frontmost", typing reported "typed 11 characters", and the
        # document stayed empty. Raising the window closes that gap.
        try:
            ax_app = AXUIElementCreateApplication(app.processIdentifier())
            window = self._best_window(ax_app)
            if window is not None:
                AXUIElementPerformAction(window, kAXRaiseAction)
                AXUIElementSetAttributeValue(window, kAXMainAttribute, True)
                time.sleep(0.2)
        except Exception:
            # Raising is best-effort; the activation above may still suffice.
            pass

        now = self.frontmost_app()
        if now and now.lower() == (app.localizedName() or "").lower():
            return ActionResult(True, f"{app.localizedName()} is now frontmost")
        return ActionResult(False, error=(
            f"Asked macOS to activate {app.localizedName()!r} but the frontmost "
            f"application is {now!r}."
        ))
