from __future__ import annotations

from PySide6.QtGui import QFont

# ==========================================================
# Font Families
# ==========================================================

SANS = ".AppleSystemUIFont"
MONO = "Menlo"

# ==========================================================
# Font Sizes
# ==========================================================

TITLE_SIZE = 24
HEADER_SIZE = 14
BODY_SIZE = 15
MESSAGE_SIZE = 15
INPUT_SIZE = 15
STATUS_SIZE = 12
SMALL_SIZE = 11

# ==========================================================
# Fonts
# ==========================================================

TITLE = QFont(SANS, TITLE_SIZE)
TITLE.setWeight(QFont.Weight.Bold)

HEADER = QFont(SANS, HEADER_SIZE)
HEADER.setWeight(QFont.Weight.DemiBold)

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

    family = MONO if mono else SANS

    f = QFont(family, size)

    f.setBold(bold)

    f.setItalic(italic)

    return f
