"""ui.instrument.tokens' platform-aware system font, and that the places
that used to hardcode `.AppleSystemUIFont` (ui/panel/style.py,
ui/theme/typography.py) now resolve through it instead of duplicating the
same macOS-only literal a third and fourth time — the exact shape of
duplication this codebase has been bitten by before (Windows-transition
audit, L1).

`.AppleSystemUIFont` is a Qt-private alias, never a real QFontDatabase
entry, so it can't be probed the way the Windows/Linux picks are — it's
returned unconditionally on Darwin and must never leak into a non-Darwin
result.
"""
from __future__ import annotations

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication(sys.argv)


def test_darwin_returns_the_private_system_font_alias(monkeypatch):
    _qapp()
    from ui.instrument import tokens

    monkeypatch.setattr(tokens.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(tokens, "_sans_cached", None)

    assert tokens.ui_sans_family() == ".AppleSystemUIFont"


def test_windows_never_returns_the_macos_alias(monkeypatch):
    _qapp()
    from ui.instrument import tokens

    monkeypatch.setattr(tokens.platform, "system", lambda: "Windows")
    monkeypatch.setattr(tokens, "_sans_cached", None)

    family = tokens.ui_sans_family()
    assert family != ".AppleSystemUIFont"
    assert family  # never empty — always a usable fallback


def test_linux_never_returns_the_macos_alias(monkeypatch):
    _qapp()
    from ui.instrument import tokens

    monkeypatch.setattr(tokens.platform, "system", lambda: "Linux")
    monkeypatch.setattr(tokens, "_sans_cached", None)

    family = tokens.ui_sans_family()
    assert family != ".AppleSystemUIFont"
    assert family


def test_result_is_cached_across_calls(monkeypatch):
    _qapp()
    from ui.instrument import tokens

    monkeypatch.setattr(tokens.platform, "system", lambda: "Windows")
    monkeypatch.setattr(tokens, "_sans_cached", None)

    first = tokens.ui_sans_family()
    # Flip the underlying platform after the first resolve — the cached
    # value must not change, matching mono_family()/serif_family()'s
    # existing cache-once behaviour.
    monkeypatch.setattr(tokens.platform, "system", lambda: "Darwin")
    assert tokens.ui_sans_family() == first


@pytest.mark.parametrize("system", ["Darwin", "Windows", "Linux"])
def test_label_family_is_always_a_nonempty_css_family_list(monkeypatch, system):
    _qapp()
    from ui.instrument import tokens

    monkeypatch.setattr(tokens.platform, "system", lambda: system)
    monkeypatch.setattr(tokens, "_sans_cached", None)

    css = tokens.label_family()
    assert isinstance(css, str) and css.strip()


@pytest.mark.parametrize("system", ["Darwin", "Windows", "Linux"])
def test_panel_style_functions_delegate_to_tokens_not_a_hardcoded_copy(monkeypatch, system):
    """ui/panel/style.py's font FUNCTIONS re-resolve on every call, so they
    can be checked live against a simulated platform."""
    _qapp()
    from ui.instrument import tokens
    from ui.panel import style

    monkeypatch.setattr(tokens.platform, "system", lambda: system)
    monkeypatch.setattr(tokens, "_sans_cached", None)
    monkeypatch.setattr(tokens, "_mono_cached", None)

    assert style.voice().family() == tokens.ui_sans_family()
    assert style.label().family() == tokens.ui_sans_family()
    assert style.mono_family() == tokens.mono_family()
    assert style.ui_family() == tokens.label_family()


def test_typography_constants_match_tokens_resolution_at_import_time():
    """ui/theme/typography.py's FONT/MONO_FONT are module-level constants,
    resolved once at import — like the codebase's other platform picks
    (mono_family() is cached the same way) — so this checks them against
    tokens' current resolution on THIS process's real platform, not a
    simulated one: the point is that they no longer carry their own second
    hardcoded '.AppleSystemUIFont' copy, not that they re-resolve live."""
    _qapp()
    from ui.instrument import tokens
    from ui.theme import typography

    assert typography.FONT == tokens.ui_sans_family()
    assert typography.MONO_FONT == tokens.mono_family()


def test_stylesheet_import_chain_survives_with_no_qapplication_yet():
    """Regression test for a real crash this change introduced and then
    fixed: ui.theme.stylesheet builds GLOBAL_STYLESHEET as a module-level
    f-string reading typography.FONT/MONO_FONT at ITS OWN import time —
    which ui/app.py imports before main() constructs a QApplication.
    QFontDatabase aborts the whole process (not a catchable exception) if
    touched before one exists, so this has to run out-of-process: a
    QApplication, once created, can't be un-created within this test
    session the way `import ui.theme.stylesheet` with none yet can be
    reproduced fresh.
    """
    result = subprocess.run(
        [sys.executable, "-c", "import ui.theme.stylesheet; print(ui.theme.stylesheet.GLOBAL_STYLESHEET[:1])"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"importing ui.theme.stylesheet with no QApplication yet must not crash "
        f"the process.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


if __name__ == "__main__":
    print("Run with pytest: pytest tests/test_ui_font_platform.py -v")
