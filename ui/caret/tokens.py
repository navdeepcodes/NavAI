"""CARET design tokens.

The whole language: a near-black ground, greyscale text, hairlines, and one
coloured object — the caret. Nothing else on screen is allowed a hue.
"""
from __future__ import annotations

from PySide6.QtGui import QFont, QFontDatabase

# ── Ground and structure ──────────────────────────────────

GROUND = "#08090C"
LIFT = "#0B0D12"
SURFACE = "#101219"
HAIRLINE = "#1B1F2B"
HAIRLINE_LIT = "#2A3350"

# ── Text registers ────────────────────────────────────────

TEXT = "#E9EBF2"
DIM = "#98A0B4"
MUTED = "#5B6379"
FAINT = "#3A4152"

# ── The caret, and only the caret ─────────────────────────
#
# INDIGO  at rest and while speaking
# CYAN    only when something is genuinely live (mic open, tool running)
# AMBER   only when Mike has stopped and is waiting on the user
# RED     only on a real raised failure

INDIGO = "#5B8CFF"
CYAN = "#4FD8E8"
AMBER = "#E5A83B"
RED = "#E56A5A"

CARET_TONE = {
    "idle": INDIGO,
    "listening": CYAN,
    "thinking": INDIGO,
    "working": CYAN,
    "needs_user": AMBER,
    "responding": INDIGO,
    "error": RED,
}

# ── Type ──────────────────────────────────────────────────

_MONO_CANDIDATES = ("SF Mono", "SFMono-Regular", "Menlo", "Monaco")


def _mono_family() -> str:
    available = set(QFontDatabase.families())
    for name in _MONO_CANDIDATES:
        if name in available:
            return name
    return "Menlo"


_mono_cached: str | None = None


def mono_family() -> str:
    global _mono_cached
    if _mono_cached is None:
        _mono_cached = _mono_family()
    return _mono_cached


SANS = ".AppleSystemUIFont"


def prose(size: int = 16, weight: int = QFont.Weight.Normal) -> QFont:
    """What Mike said."""
    font = QFont(SANS, size)
    font.setWeight(weight)
    font.setStyleStrategy(QFont.PreferAntialias)
    return font


def machine(size: int = 12, weight: int = QFont.Weight.Normal) -> QFont:
    """What Mike observed or did. Never used for Mike's own words."""
    font = QFont(mono_family(), size)
    font.setWeight(weight)
    font.setStyleStrategy(QFont.PreferAntialias)
    return font


# ── Metrics ───────────────────────────────────────────────

COLUMN = 700          # measure of the reading column at D3
GUTTER = 40
CARET_W = 3           # edge / composer
CARET_H = 15
CARET_W_HOME = 6      # the one at the head of the column
CARET_H_HOME = 32
