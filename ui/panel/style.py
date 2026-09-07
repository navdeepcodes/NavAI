"""The visual system for Mike's surface. Small on purpose.

One ground, one ink, one accent, a handful of tones between them, and two
type sizes that matter. Everything Mike shows is built from these, so the
product reads as one considered thing rather than an assembly of components.

The break from the old instrument is in the *material*, not just the hue: a
warm-dark system surface that floats over your desktop like a command
palette, not a cream page set into a metal housing. The accent is the one
warm, living colour — and it is the thing a user personalises, so it lives in
exactly one place here and is read, never hard-coded, everywhere else.
"""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont

# ── Ground: a warm-dark surface, faintly translucent so it reads as a
#    system layer over whatever you were doing, not an opaque app window. ──
GROUND = "#15161A"          # the panel body
GROUND_RAISED = "#1C1E23"   # inset surfaces (input, confirmation)
GROUND_SUNK = "#101114"     # the deepest recesses
HAIRLINE = "#26282E"        # the only borders that exist, and only where earned

# ── Ink: warm near-white, so the surface feels humane rather than clinical.
INK = "#EDEAE3"             # what Mike says; what you type
INK_SOFT = "#B7B3AA"        # secondary text
INK_MUTE = "#7C7871"        # labels, timestamps, the quiet layer
INK_FAINT = "#4E4B46"       # the faintest structural marks

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


# ── Type. System sans throughout — this is a desktop app, not a web page.
#    Mike's voice a touch larger; labels small and quietly spaced. Mono only
#    for genuinely technical detail (a path, a command) shown on demand.
_UI = ".AppleSystemUIFont"
_MONO = "SF Mono, Menlo, monospace"


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
    return "-apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif"
