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

_MONO_CANDIDATES = ("SF Mono", "SFMono-Regular", "Menlo", "Monaco")
_SERIF_CANDIDATES = ("Georgia", "New York", "Times New Roman")

_mono_cached: str | None = None
_serif_cached: str | None = None


def _pick(candidates: tuple[str, ...], fallback: str) -> str:
    available = set(QFontDatabase.families())
    for name in candidates:
        if name in available:
            return name
    return fallback


def mono_family() -> str:
    global _mono_cached
    if _mono_cached is None:
        _mono_cached = _pick(_MONO_CANDIDATES, "Menlo")
    return _mono_cached


def serif_family() -> str:
    """The logbook's hand — a warm serif for what Mike actually says."""
    global _serif_cached
    if _serif_cached is None:
        _serif_cached = _pick(_SERIF_CANDIDATES, "Georgia")
    return _serif_cached


LABEL_SANS = ".AppleSystemUIFont"


def label(size: int = 11, weight: int = QFont.Weight.DemiBold) -> QFont:
    """Engraved panel labels — small, spaced, uppercase by convention."""
    font = QFont(LABEL_SANS, size)
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
    font = QFont(LABEL_SANS, size)
    font.setWeight(weight)
    return font


def qcolor(hexstr: str) -> QColor:
    return QColor(hexstr)
