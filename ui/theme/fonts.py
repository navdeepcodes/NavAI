from __future__ import annotations

from PySide6.QtGui import QFont


# ==========================================================
# Font Families
# ==========================================================

# Temporary system fonts.
# Later we'll bundle Inter and JetBrains Mono with the app.

SANS = "Helvetica Neue"
MONO = "Menlo"


# ==========================================================
# Font Sizes
# ==========================================================

TITLE_SIZE = 22
HEADER_SIZE = 14
BODY_SIZE = 13
MESSAGE_SIZE = 14
INPUT_SIZE = 14
STATUS_SIZE = 11
SMALL_SIZE = 10


# ==========================================================
# Fonts
# ==========================================================

TITLE = QFont(MONO, TITLE_SIZE)
TITLE.setBold(True)

HEADER = QFont(SANS, HEADER_SIZE)
HEADER.setBold(True)

BODY = QFont(SANS, BODY_SIZE)

MESSAGE = QFont(SANS, MESSAGE_SIZE)

INPUT = QFont(SANS, INPUT_SIZE)

STATUS = QFont(SANS, STATUS_SIZE)

SMALL = QFont(SANS, SMALL_SIZE)


# ==========================================================
# Helper
# ==========================================================

def font(
    size: int,
    *,
    bold: bool = False,
    italic: bool = False,
    mono: bool = False,
) -> QFont:
    """
    Create a font with the Mike design system.

    Example:
        label.setFont(font(16, bold=True))
    """

    family = MONO if mono else SANS

    f = QFont(family, size)

    f.setBold(bold)

    f.setItalic(italic)

    return f