"""The visual system for Mike's surface. Small on purpose.

One ground, one ink, one accent, a handful of tones between them, and two
type sizes that matter. Everything Mike shows is built from these, so the
product reads as one considered thing rather than an assembly of components.

The palette itself is read from huddlecode.com's own stylesheet (paper/ink/
graphite/mist), not a separate app-side guess at what "matches the website"
means — the app and the site are one product, and this is the actual source
of truth for what that product looks like. The accent stays the one
exception: the site is deliberately monochrome ("No accent color" — its own
words), but a personal accent Mike's users can choose is a real product
feature of the *app*, not the marketing page, so it lives on outside this
alignment, in exactly one place, read rather than hard-coded everywhere else.
"""
from __future__ import annotations

import platform

from PySide6.QtGui import QColor, QFont

# ── Ground: the site's own "paper" system -- huddlecode.com/styles.css
#    :root { --paper / --paper-dim / --paper-dim-2 / --mist }, read directly
#    rather than re-guessed here.
GROUND = "#FAF9F7"          # the panel body (--paper)
GROUND_RAISED = "#F1EFEB"   # inset surfaces (input, confirmation) (--paper-dim)
GROUND_SUNK = "#EBE9E4"     # the deepest recesses (--paper-dim-2)
HAIRLINE = "#DEDCD6"        # the only borders that exist, and only where earned (--mist)

# ── Ink: the site's own --ink/--graphite/--graphite-2/--mist-2.
INK = "#0D0D0C"             # what Mike says; what you type (--ink)
INK_SOFT = "#55534F"        # secondary text (--graphite)
INK_MUTE = "#79766F"        # labels, timestamps, the quiet layer (--graphite-2)
INK_FAINT = "#CECBC3"       # the faintest structural marks (--mist-2)

# ── The accent: warm, living, personal. Read from preferences everywhere so
#    a user's chosen colour flows through the whole surface from one setting.
_DEFAULT_ACCENT = "#E7A54F"   # a warm amber-gold — presence, not decoration
_ACCENT_PRESETS = {
    "amber":  "#E7A54F",
    "coral":  "#E8795B",
    "sky":    "#5AA6E0",
    "sage":   "#8DB87A",
    "orchid": "#B98AD6",
}

# Semantic signal — separate from the accent, never used decoratively.
GOOD = "#7FB37A"            # a step finished, and it worked
WARN = "#E7A54F"            # needs you (shares the accent's warmth on purpose)
STOP = "#E06A54"            # a real failure, or a destructive confirmation


def accent() -> str:
    """Mike's colour. The user's if they've chosen one, the default otherwise."""
    try:
        from config import preferences

        chosen = str(preferences.get("accent", "") or "").strip().lower()
        if chosen in _ACCENT_PRESETS:
            return _ACCENT_PRESETS[chosen]
        if chosen.startswith("#") and len(chosen) in (4, 7):
            return chosen
    except Exception:
        pass
    return _DEFAULT_ACCENT


def accent_presets() -> dict[str, str]:
    return dict(_ACCENT_PRESETS)


def qaccent() -> QColor:
    return QColor(accent())


# ── Type. Each platform's own native UI font, not the site's Fraunces/
#    Archivo web fonts — this is a desktop app, not a page rendering them.
#    ".AppleSystemUIFont" was never a font Windows has; Qt silently
#    substituted something else for every label in the app, verified
#    directly on this machine. Segoe UI is Windows' real equivalent of the
#    system font macOS already got here. Mike's voice a touch larger;
#    labels small and quietly spaced. Mono only for genuinely technical
#    detail (a path, a command) shown on demand.
_UI = "Segoe UI" if platform.system() == "Windows" else ".AppleSystemUIFont"
_MONO = (
    "Consolas, 'Cascadia Mono', monospace" if platform.system() == "Windows"
    else "SF Mono, Menlo, monospace"
)


def voice(size: int = 15) -> QFont:
    """What Mike says, and what you type — the reading size."""
    f = QFont(_UI, size)
    f.setWeight(QFont.Weight.Normal)
    return f


def label(size: int = 11, weight: QFont.Weight = QFont.Weight.DemiBold) -> QFont:
    f = QFont(_UI, size)
    f.setWeight(weight)
    return f


def mono_family() -> str:
    return _MONO


def ui_family() -> str:
    if platform.system() == "Windows":
        return "'Segoe UI', Arial, sans-serif"
    return "-apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif"
