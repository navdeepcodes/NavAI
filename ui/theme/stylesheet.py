from __future__ import annotations

from ui.theme import colors


GLOBAL_STYLESHEET = f"""

QMainWindow {{
    background:{colors.BACKGROUND};
}}

QWidget {{
    background:{colors.BACKGROUND};
    color:{colors.TEXT};
}}

QFrame {{
    background:{colors.SURFACE};
    border:1px solid {colors.BORDER};
}}

QLineEdit,
QPlainTextEdit {{

    background:{colors.SURFACE};

    color:{colors.TEXT};

    border:1px solid {colors.BORDER};

    padding:14px;

    selection-background-color:{colors.ACCENT};

    font-size:14px;

}}

QScrollArea {{

    border:none;

}}

QScrollBar:vertical {{

    width:8px;

    background:transparent;

}}

QScrollBar::handle:vertical {{

    background:{colors.BORDER};

    border-radius:4px;

}}

QPushButton {{

    background:transparent;

    color:{colors.TEXT};

    border:none;

}}

QPushButton:hover {{

    color:{colors.ACCENT};

}}

"""