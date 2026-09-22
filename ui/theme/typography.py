from __future__ import annotations

from ui.instrument import tokens as _tokens

# ==========================================================
# Font Families
# ==========================================================
#
# Resolved per platform by ui.instrument.tokens (Segoe UI on Windows,
# San Francisco on macOS, a probed Linux fallback) instead of hardcoding
# macOS-only family names.
#
# Resolved lazily (module __getattr__, PEP 562) rather than as plain
# assignments: ui.instrument.tokens' resolvers call QFontDatabase, which
# aborts the process if no QApplication exists yet — and this module is
# reachable from plain imports (e.g. ui.widgets.conversation.*) well before
# ui/app.py constructs one. FONT/MONO_FONT keep working as ordinary module
# attributes for the ~10 existing call sites; they just aren't computed
# until first actually read, by which point a QApplication is running.


def __getattr__(name: str):
    if name == "FONT":
        return _tokens.ui_sans_family()
    if name == "MONO_FONT":
        return _tokens.mono_family()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

# ==========================================================
# Font Sizes
# ==========================================================

TITLE = 24
SUBTITLE = 16

SECTION = 15
BODY = 15

SMALL = 13
TINY = 11

# ==========================================================
# Weights
# ==========================================================

LIGHT = 300
REGULAR = 400
MEDIUM = 500
SEMIBOLD = 600
BOLD = 700
