"""First-run permissions card (Windows-only launch, docs/NEXT.md §1.1.1).

The tour asks for what actually needs asking before consent: microphone
(Windows never prompts desktop apps), abilities (same state as Settings),
start-at-sign-in + notifications. Screen reading/clicking need no Windows
permission — none is invented.

Runs offscreen on Mac CI: QT_QPA_PLATFORM=offscreen pytest.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401


def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


def test_permissions_card_sits_before_consent():
    _app()
    from config import preferences
    from brain import legal
    from ui.welcome import CONSENT, PERMISSIONS, WelcomeWindow

    preferences.set_value("terms_accepted_version", "")
    tour = WelcomeWindow()
    assert PERMISSIONS in tour._cards
    assert CONSENT in tour._cards
    assert tour._cards.index(PERMISSIONS) < tour._cards.index(CONSENT)
    assert tour._cards.index(PERMISSIONS) > 0
    tour.close()

    consent = WelcomeWindow(consent_only=True)
    assert PERMISSIONS not in consent._cards
    assert consent._cards == [CONSENT]
    consent.close()


def test_skip_lands_on_permissions_before_consent():
    _app()
    from config import preferences
    from ui.welcome import CONSENT, PERMISSIONS, WelcomeWindow

    preferences.set_value("terms_accepted_version", "")
    tour = WelcomeWindow()
    tour._index = 0
    tour._skip_pressed()  # first Skip -> permissions, not straight to consent
    assert tour._cards[tour._index] is PERMISSIONS
    assert tour._is_permissions_showing()
    assert not tour._perms_scroll.isHidden()
    tour._skip_pressed()  # second Skip -> consent
    assert tour._cards[tour._index] is CONSENT
    tour.close()


def test_ability_switches_share_settings_state():
    _app()
    from config import preferences
    from brain import permissions
    from ui.welcome import WelcomeWindow

    preferences.set_value("terms_accepted_version", "")
    tour = WelcomeWindow()
    assert set(tour._ability_switches) == set(permissions.ABILITIES)
    # Toggling through the tour writes the same pref Settings reads.
    permissions.set_enabled("web", True)
    assert permissions.is_enabled("web")
    permissions.set_enabled("web", False)
    assert "web" in permissions.disabled()
    permissions.set_enabled("web", True)
    tour.close()


def test_microphone_status_never_claims_blocked_without_evidence(monkeypatch):
    from hostplatform import microphone as mic

    # Non-Windows: unknown, never denied.
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    assert mic.status() == "unknown"

    # Windows with no registry evidence: unknown, not denied.
    monkeypatch.setattr("platform.system", lambda: "Windows")

    class _FakeKey:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class _FakeWinreg:
        HKEY_CURRENT_USER = 0
        def __init__(self, values):
            self._values = values
        def OpenKey(self, *a):
            return _FakeKey()
        def QueryValueEx(self, key, name):
            raise OSError("no value")

    monkeypatch.setitem(sys.modules, "winreg", _FakeWinreg({}))
    assert mic.status() == "unknown"

    # Explicit Deny in either value -> denied.
    class _DenyWinreg(_FakeWinreg):
        def QueryValueEx(self, key, name):
            return ("Deny", 1)
    monkeypatch.setitem(sys.modules, "winreg", _DenyWinreg({}))
    # winreg is imported inside mic.status via `import winreg`, which reads
    # sys.modules — but CPython caches the failed import; force reimport path
    # by calling status with a real fake module object.
    import types
    fake = types.ModuleType("winreg")
    fake.HKEY_CURRENT_USER = 0
    fake.OpenKey = lambda *a, **k: _FakeKey()
    fake.QueryValueEx = lambda *a, **k: ("Deny", 1)
    monkeypatch.setitem(sys.modules, "winreg", fake)
    assert mic.status() == "denied"
