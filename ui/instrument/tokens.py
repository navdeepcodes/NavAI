"""Instrument design tokens.

Mike as a machined dial, not a chat bubble. Two materials: a dark metal
housing (the instrument itself — dial, counter, room switches) and a paper
logbook set into it (the actual conversation, ink on cream).

Colour has exactly three meanings and nothing decorative:
  AMBER  Mike is doing something right now
  RED    Mike has stopped and needs you (flag + redline), or a real failure
  GREEN  finished, and it worked
No legend is ever shown in the product — the shapes (a resting needle, a
raised flag, a lit LED) are meant to be self-explanatory the way a real
instrument's are.
"""
from __future__ import annotations

import platform

from PySide6.QtGui import QColor, QFont, QFontDatabase

# ── Housing (dark metal) ─────────────────────────────────

GROUND = "#17140F"
PANEL = "#221D17"
BEZEL = "#2A251E"
HAIRLINE = "#2E2820"
METAL_HI = "#5B5347"
METAL_LO = "#221D17"

TEXT = "#EDE6D9"
DIM = "#9C968A"
MUTED = "#6B6355"
FAINT = "#4A443C"

# ── Signal ────────────────────────────────────────────────

AMBER = "#E8935A"
RED = "#D9573F"
GREEN = "#7FA87A"

DIAL_TONE = {
    "idle": AMBER,
    "listening": AMBER,
    "thinking": AMBER,
    "working": AMBER,
    "responding": AMBER,
    "needs_user": RED,
    "error": RED,
    "done": GREEN,
}

# ── Logbook (paper) ───────────────────────────────────────

PAPER = "#EDE6D9"
PAPER_RULE = "rgba(42, 38, 32, 0.07)"
INK = "#2A2620"
INK_DIM = "#8A7F6E"
INK_ACCENT = "#B8571F"

# ── Type ──────────────────────────────────────────────────

_MONO_CANDIDATES = (
    "SF Mono", "SFMono-Regular", "Menlo", "Monaco",
    "Cascadia Mono", "Cascadia Code", "Consolas",
    "DejaVu Sans Mono",
)
_SERIF_CANDIDATES = ("Georgia", "New York", "Times New Roman")
_WIN_SANS_CANDIDATES = ("Segoe UI Variable Text", "Segoe UI Variable", "Segoe UI")
_LINUX_SANS_CANDIDATES = ("Ubuntu", "Cantarell", "Noto Sans", "DejaVu Sans")

_mono_cached: str | None = None
_serif_cached: str | None = None
_sans_cached: str | None = None


def _qapp_ready() -> bool:
    """Whether a QApplication already exists.

    QFontDatabase aborts the whole process (not a catchable exception) if
    queried before one does. This module is reachable from plain imports —
    ui.theme.stylesheet builds GLOBAL_STYLESHEET as a module-level f-string
    that reads these fonts at ITS OWN import time, which ui/app.py imports
    before main() constructs a QApplication — so every probe here has to
    check first rather than assume a caller already has a window open.
    """
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() is not None


def _pick(candidates: tuple[str, ...], fallback: str) -> str:
    if not _qapp_ready():
        return fallback
    available = set(QFontDatabase.families())
    for name in candidates:
        if name in available:
            return name
    return fallback


def mono_family() -> str:
    global _mono_cached
    if _mono_cached is not None:
        return _mono_cached
    value = _pick(_MONO_CANDIDATES, "Menlo")
    # Only memoize once a QApplication actually let this probe QFontDatabase
    # for real — caching the pre-QApplication fallback would permanently
    # deny every later, capable caller the chance to find a better match.
    if _qapp_ready():
        _mono_cached = value
    return value


def serif_family() -> str:
    """The logbook's hand — a warm serif for what Mike actually says."""
    global _serif_cached
    if _serif_cached is not None:
        return _serif_cached
    value = _pick(_SERIF_CANDIDATES, "Georgia")
    if _qapp_ready():
        _serif_cached = value
    return value


def ui_sans_family() -> str:
    """The system UI font, resolved per platform.

    macOS: Qt's private `.AppleSystemUIFont` alias always resolves to San
    Francisco and is never a real entry in QFontDatabase — it can't be
    probed the way mono_family()/serif_family() are, so it's returned
    unconditionally on Darwin. Windows and Linux have no such alias, so
    they probe QFontDatabase for what's actually installed, same as the
    other picks in this file.
    """
    global _sans_cached
    if _sans_cached is not None:
        return _sans_cached
    system = platform.system()
    if system == "Darwin":
        # A fixed sentinel, not a QFontDatabase probe — safe to cache
        # unconditionally, no QApplication required.
        _sans_cached = ".AppleSystemUIFont"
        return _sans_cached
    if system == "Windows":
        value = _pick(_WIN_SANS_CANDIDATES, "Segoe UI")
    else:
        value = _pick(_LINUX_SANS_CANDIDATES, "sans-serif")
    if _qapp_ready():
        _sans_cached = value
    return value


def label_family() -> str:
    """The instrument's engraved-label typeface as a CSS font-family list,
    for rich-text spans that need to name it explicitly rather than take it
    from a QFont."""
    system = platform.system()
    if system == "Darwin":
        return "-apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif"
    if system == "Windows":
        return f"'{ui_sans_family()}', 'Segoe UI', sans-serif"
    return f"'{ui_sans_family()}', sans-serif"


def label(size: int = 11, weight: int = QFont.Weight.DemiBold) -> QFont:
    """Engraved panel labels — small, spaced, uppercase by convention."""
    font = QFont(ui_sans_family(), size)
    font.setWeight(weight)
    font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 108)
    return font


def machine(size: int = 12) -> QFont:
    font = QFont(mono_family(), size)
    return font


def prose(size: int = 16, italic: bool = False) -> QFont:
    font = QFont(serif_family(), size)
    font.setItalic(italic)
    return font


def sans(size: int = 15, weight: int = QFont.Weight.Normal) -> QFont:
    font = QFont(ui_sans_family(), size)
    font.setWeight(weight)
    return font


def qcolor(hexstr: str) -> QColor:
    return QColor(hexstr)
