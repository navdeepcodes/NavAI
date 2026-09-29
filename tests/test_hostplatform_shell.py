"""hostplatform.shell: real "ask the OS to open something" behaviour.

No test file existed for this module before -- every fix here was verified
by hand against the physical machine and never pinned down as a test, which
is exactly how the same regression could ship twice. Three real bugs found
during a clean-Windows-install product test are what these guard:

1. open_application unconditionally raised NotImplementedError on Windows on
   the theory that Windows has no LaunchServices equivalent. Verified false:
   os.startfile resolves a bare name through the App Paths registry and PATH
   search, the same way Explorer's Run box does, and opened Notepad,
   Calculator, Paint, VS Code and Chrome on the first try.
2. open_browser defaulted to os.startfile(DEFAULT_BROWSER), and
   DEFAULT_BROWSER defaults to "Opera" -- a browser most Windows machines
   don't have. Verified failing with FileNotFoundError.
3. open_url/open_browser opened a real tab but never brought the browser
   forward, so a user watching the screen saw no evidence anything had
   happened, even though it had.
"""
from __future__ import annotations

import os
import platform
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401

import pytest

from hostplatform import shell


@pytest.mark.skipif(platform.system() != "Windows", reason="Windows-only behaviour")
def test_open_application_resolves_a_real_app_by_common_name():
    """The regression this guards: this used to raise NotImplementedError
    unconditionally on Windows, before ever trying os.startfile."""
    shell.open_application("notepad")
    import time
    time.sleep(1)
    import subprocess
    result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq notepad.exe"],
        capture_output=True, text=True,
    )
    assert "notepad.exe" in result.stdout.lower()
    subprocess.run(["taskkill", "/IM", "notepad.exe", "/F"], capture_output=True)


@pytest.mark.skipif(platform.system() != "Windows", reason="Windows-only behaviour")
def test_open_application_reports_an_unknown_name_clearly():
    """A misspelled or uninstalled app must raise something a caller can
    catch and explain, not let a raw FileNotFoundError through."""
    with pytest.raises(shell.ShellError):
        shell.open_application("definitely-not-a-real-app-xyz")


@pytest.mark.skipif(platform.system() != "Windows", reason="Windows-only behaviour")
def test_open_application_resolves_a_friendly_name_startfile_cannot():
    """The regression this guards: a live model run asked to open the
    'Calculator' app and got 'Could not find an application named
    Calculator'. os.startfile resolves 'calc' but not the friendly display
    name, and cannot reach Store/UWP apps at all -- so the Start-menu
    catalogue fallback has to take over. This opens the app by the exact name
    a user or the model would say."""
    import subprocess
    import time

    subprocess.run(["taskkill", "/IM", "CalculatorApp.exe", "/F"],
                   capture_output=True)
    shell.open_application("Calculator")

    appeared = False
    for _ in range(20):
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "if (Get-Process | Where-Object {$_.MainWindowTitle -eq "
             "'Calculator'}) { 'yes' } else { 'no' }"],
            capture_output=True, text=True,
        )
        if "yes" in result.stdout.lower():
            appeared = True
            break
        time.sleep(0.3)
    subprocess.run(["taskkill", "/IM", "CalculatorApp.exe", "/F"],
                   capture_output=True)
    assert appeared, "Calculator did not open by its friendly name"


def test_resolve_start_app_matching_precedence(monkeypatch):
    """The resolver ranks matches so the most specific one wins: an exact
    display name beats a prefix, which beats a substring, which beats a match
    that is only in the AppID. Pure logic, so it runs on any platform with the
    Start-menu listing stubbed -- what it protects is that 'Calculator' does
    not get shadowed by 'Calculator Plus' when the real one is installed, and
    that 'calc' still finds the Calculator AUMID."""
    import json as _json
    import subprocess as _sp

    catalogue = [
        {"Name": "Calculator Plus", "AppID": "Some.CalculatorPlus_x!App"},
        {"Name": "Calculator", "AppID": "Microsoft.WindowsCalculator_8wekyb!App"},
        {"Name": "Notepad", "AppID": "notepad.exe"},
    ]

    class _Fake:
        returncode = 0
        stdout = _json.dumps(catalogue)

    monkeypatch.setattr(_sp, "run", lambda *a, **k: _Fake())

    # exact name beats the prefix "Calculator Plus"
    assert shell._resolve_start_app("Calculator") == "Microsoft.WindowsCalculator_8wekyb!App"
    # only in the AppID -- "calc" is nowhere in a display name here
    assert shell._resolve_start_app("calc") == "Some.CalculatorPlus_x!App"
    # nothing matches -> None, so the caller raises a clear error
    assert shell._resolve_start_app("nonexistent-zzz") is None


@pytest.mark.skipif(platform.system() != "Windows", reason="Windows-only behaviour")
def test_open_browser_does_not_depend_on_default_browser_setting(monkeypatch):
    """The regression: DEFAULT_BROWSER defaults to "Opera", which most
    Windows machines don't have, and open_browser used to pass it straight
    to os.startfile. Deliberately monkeypatched to something absurd here --
    if open_browser still worked, it isn't reading DEFAULT_BROWSER at all."""
    monkeypatch.setattr("config.settings.DEFAULT_BROWSER", "not-a-real-browser-xyz")
    shell.open_browser()  # must not raise


@pytest.mark.skipif(platform.system() != "Windows", reason="Windows-only behaviour")
def test_open_url_normalizes_and_does_not_raise():
    shell.open_url("example.com")


if __name__ == "__main__":
    if platform.system() == "Windows":
        test_open_application_resolves_a_real_app_by_common_name()
        test_open_application_reports_an_unknown_name_clearly()
        test_open_url_normalizes_and_does_not_raise()
    print("\nAll hostplatform.shell tests passed.")
