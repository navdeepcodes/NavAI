"""The visual system for Mike's surface. Small on purpose.

One ground, one ink, one accent, a handful of tones between them, and two
type sizes that matter. Everything Mike shows is built from these, so the
product reads as one considered thing rather than an assembly of components.

The palette itself is read from huddlecode.com's own stylesheet (paper/ink/
graphite/mist), not a separate app-side guess at what "matches the website"
means — the app and the site are one product, and this is the actual source
of truth for what that product looks like. The accent stays the one
exception: the site is deliberately monochrome ("No accent color" — its own
words), but a personal accent Mike's users can choose is a real product
feature of the *app*, not the marketing page, so it lives on outside this
alignment, in exactly one place, read rather than hard-coded everywhere else.
"""
from __future__ import annotations

import platform

from PySide6.QtGui import QColor, QFont

# ── Two grounds, one language. Light is the site's own "paper" system
#    (huddlecode.com/styles.css --paper/--mist/--ink), read directly. Dark is
#    its inverse in the same warm key — a dim-lit room, not cold black, so the
#    product still reads as paper-and-ink after dark rather than as a different
#    app. The module-level tokens below are set from whichever is active; every
#    widget reads style.GROUND / style.INK etc. at paint or build time, so
#    apply_theme() before the UI is built is all it takes to dress the whole
#    surface either way.
_LIGHT = {
    "GROUND": "#FAF9F7", "GROUND_RAISED": "#F1EFEB", "GROUND_SUNK": "#EBE9E4",
    "HAIRLINE": "#DEDCD6",
    "INK": "#0D0D0C", "INK_SOFT": "#55534F", "INK_MUTE": "#79766F",
    "INK_FAINT": "#CECBC3",
    # the lifted surface a hand rests on: the composer, the corner card
    "SURFACE": "#FFFFFF",
}
_DARK = {
    "GROUND": "#1A1917", "GROUND_RAISED": "#232220", "GROUND_SUNK": "#131210",
    "HAIRLINE": "#322F2A",
    "INK": "#F3F1EC", "INK_SOFT": "#BEB9B0", "INK_MUTE": "#8C877E",
    "INK_FAINT": "#46433D",
    "SURFACE": "#262421",
}

# Set at import to light, replaced by apply_theme() at startup. Declared here so
# every `style.GROUND` reference has something to bind to before apply runs.
GROUND = _LIGHT["GROUND"]
GROUND_RAISED = _LIGHT["GROUND_RAISED"]
GROUND_SUNK = _LIGHT["GROUND_SUNK"]
HAIRLINE = _LIGHT["HAIRLINE"]
INK = _LIGHT["INK"]
INK_SOFT = _LIGHT["INK_SOFT"]
INK_MUTE = _LIGHT["INK_MUTE"]
INK_FAINT = _LIGHT["INK_FAINT"]
SURFACE = _LIGHT["SURFACE"]

_ACTIVE_THEME = "light"


def _os_theme() -> str:
    """'dark' or 'light' from the operating system, best-effort.

    Qt 6.5+ exposes the OS setting directly; older Qt (or a headless read)
    falls back to the Windows registry, then to light. Never raises — a theme
    guess must not be able to stop the app from starting.
    """
    try:
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtCore import Qt as _Qt

        hints = QGuiApplication.styleHints()
        scheme = getattr(hints, "colorScheme", None)
        if scheme is not None:
            value = scheme()
            if value == _Qt.ColorScheme.Dark:
                return "dark"
            if value == _Qt.ColorScheme.Light:
                return "light"
    except Exception:
        pass
    if platform.system() == "Windows":
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return "light" if value else "dark"
        except Exception:
            pass
    return "light"


def resolve_theme() -> str:
    """The theme to use: the user's explicit choice, or else the OS setting."""
    try:
        from config import preferences

        pref = str(preferences.get("theme", "system") or "system").strip().lower()
        if pref in ("light", "dark"):
            return pref
    except Exception:
        pass
    return _os_theme()


def apply_theme(name: str | None = None) -> str:
    """Dress the whole surface light or dark. Returns the theme applied.

    Reassigns the module-level tokens, so any widget built or repainted after
    this reads the active palette. Call it once before the UI is built, and
    again (followed by a repaint) if the OS theme changes while Mike is open.
    """
    global _ACTIVE_THEME
    name = (name or resolve_theme())
    palette = _DARK if name == "dark" else _LIGHT
    globals().update(palette)
    _ACTIVE_THEME = name
    return name


def active_theme() -> str:
    return _ACTIVE_THEME


def is_dark() -> bool:
    return _ACTIVE_THEME == "dark"

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


# ── Type. Mike speaks in one face: Source Serif 4 (Adobe, SIL Open Font
#    License), bundled in ui/fonts and registered at startup by load_fonts(),
#    so it looks the same on every machine rather than depending on what a
#    user happens to have installed. A calm, bookish serif reads like
#    something written for you — the register of a thoughtful assistant, not
#    a control panel. The platform's own UI face stays as the fallback, used
#    only if the bundled files can't be loaded: Segoe UI on Windows (never
#    ".AppleSystemUIFont", which Windows doesn't have and silently replaced),
#    the system face on macOS. Mono only for genuinely technical detail.
BRAND_FAMILY = "Source Serif 4"
_SYSTEM_UI = "Segoe UI" if platform.system() == "Windows" else ".AppleSystemUIFont"
_UI = _SYSTEM_UI
_FONTS_LOADED = False
_MONO = (
    "Consolas, 'Cascadia Mono', monospace" if platform.system() == "Windows"
    else "SF Mono, Menlo, monospace"
)


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


def _fonts_dir():
    """Where the bundled font files live: beside the frozen app, or in the
    source tree."""
    import os
    import sys
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for base in (os.path.join(getattr(sys, "_MEIPASS", ""), "ui"), here):
        path = os.path.join(base, "fonts")
        if base and os.path.isdir(path):
            return path
    return None


def load_fonts() -> bool:
    """Register the bundled Source Serif 4 files and make it Mike's face.

    Needs a QApplication. Safe to call more than once. If the files are
    missing or refused, Mike keeps the platform's UI font — a fallback, never
    a crash and never a blank label.
    """
    global _UI, _FONTS_LOADED
    if _FONTS_LOADED:
        return True
    try:
        import os
        from PySide6.QtGui import QFontDatabase

        folder = _fonts_dir()
        if folder is None:
            return False
        families: set[str] = set()
        for name in sorted(os.listdir(folder)):
            if name.lower().endswith((".ttf", ".otf")):
                fid = QFontDatabase.addApplicationFont(os.path.join(folder, name))
                if fid >= 0:
                    families.update(QFontDatabase.applicationFontFamilies(fid))
        if BRAND_FAMILY in families:
            _UI = BRAND_FAMILY
            _FONTS_LOADED = True
            return True
    except Exception:
        pass
    return False


def ui_face() -> str:
    """The family every widget is drawn in right now."""
    return _UI


# ── The type scale. Pixel sizes, not points: Mike's rich text (replies, code,
#    maths) is HTML and speaks px, so widgets sized in px sit on exactly the
#    same scale as the text beside them. Every surface of the workspace takes
#    its sizes from here, so hierarchy is a property of the product rather
#    than of whichever file a label happens to live in.
DISPLAY = 28      # page titles, the greeting on an empty chat
TITLE = 20        # a section heading, a dialog title
READ = 16         # what Mike says, what you said — the reading size
BODY = 14         # controls, list rows, settings copy
SMALL = 13        # secondary copy
CAPTION = 12      # meta: times, counts, hints
MICRO = 11        # section labels


def font(px: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    """The UI face at a pixel size from the scale above."""
    f = QFont(_UI)
    f.setPixelSize(int(px))
    f.setWeight(weight)
    return f


def reduced_motion() -> bool:
    """Calm the interface: the user's own switch in Settings, or the OS's.

    One answer for every animated surface, so the Settings switch is a real
    control rather than a preference that is saved and then read by nothing.
    """
    try:
        from config import preferences
        if bool(preferences.get("reduced_motion", False)):
            return True
    except Exception:
        pass
    try:
        from hostplatform.desktop import reduced_motion as _os_reduced
        return bool(_os_reduced())
    except Exception:
        return False


def ui_family() -> str:
    """The same face for rich text (Mike's rendered replies), as CSS."""
    system = ("'Segoe UI', Arial, sans-serif" if platform.system() == "Windows"
              else "-apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif")
    if _FONTS_LOADED:
        return f"'{BRAND_FAMILY}', Georgia, {system}"
    return system
