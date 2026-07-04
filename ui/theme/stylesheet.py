from __future__ import annotations

from ui.theme import colors
from ui.theme import typography


GLOBAL_STYLESHEET = f"""

/* =========================================================
   Application
   ========================================================= */

QMainWindow {{
    background: {colors.WINDOW};
}}

QWidget {{
    background: transparent;
    color: {colors.TEXT};
    font-family: "{typography.FONT}";
    font-size: {typography.BODY}px;
    selection-background-color: {colors.SELECTION};
}}

/* =========================================================
   Generic Frames
   ========================================================= */

QFrame {{
    border: none;
    background: transparent;
}}

/* =========================================================
   Labels
   ========================================================= */

QLabel {{
    background: transparent;
    color: {colors.TEXT};
}}

/* =========================================================
   Scroll Areas
   ========================================================= */

QScrollArea {{
    border: none;
    background: transparent;
}}

QScrollArea > QWidget > QWidget {{
    background: transparent;
}}

/* =========================================================
   Scroll Bars
   ========================================================= */

QScrollBar:vertical {{
    width: 8px;
    background: transparent;
}}

QScrollBar::handle:vertical {{
    background: {colors.BORDER};
    border-radius: 4px;
    min-height: 40px;
}}

QScrollBar::handle:vertical:hover {{
    background: {colors.TEXT_MUTED};
}}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {{
    height: 0px;
    background: transparent;
}}

QScrollBar:horizontal {{
    height: 0px;
}}

"""