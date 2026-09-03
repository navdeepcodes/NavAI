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
    width: 6px;
    background: transparent;
    margin: 4px 0;
}}

QScrollBar::handle:vertical {{
    background: {colors.BORDER};
    border-radius: 3px;
    min-height: 32px;
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

/* =========================================================
   Message Box (Confirmation Dialog)
   ========================================================= */

QMessageBox {{
    background: {colors.SURFACE};
}}

QMessageBox QLabel {{
    color: {colors.TEXT};
    font-size: {typography.BODY}px;
    padding: 8px 4px;
}}

QMessageBox QPushButton {{
    background: {colors.SURFACE_ELEVATED};
    border: 1px solid {colors.BORDER};
    border-radius: 8px;
    color: {colors.TEXT};
    font-size: {typography.SMALL}px;
    font-weight: 500;
    min-width: 80px;
    padding: 8px 20px;
}}

QMessageBox QPushButton:hover {{
    background: {colors.SURFACE_HOVER};
    border-color: {colors.BORDER_STRONG};
}}

QMessageBox QPushButton:pressed {{
    background: {colors.SURFACE_ACTIVE};
}}

"""
