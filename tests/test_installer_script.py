"""The Windows installer script and Mike's own installer must agree.

packaging/mike.iss builds Mike-Setup-<version>.exe. It cannot be run on a
Mac, so the decisions that would only fail on a user's PC are pinned here as
text checks. The real install/update/uninstall is exercised on a Windows
machine by the "Smoke-test the installer" step of windows-build.yml.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ISS = (REPO / "packaging" / "mike.iss").read_text(encoding="utf-8")
WORKFLOW = (REPO / ".github" / "workflows" / "windows-build.yml").read_text(encoding="utf-8")


def _setting(name: str) -> str:
    match = re.search(rf"^{name}=(.+)$", ISS, re.M)
    assert match, f"mike.iss has no {name}="
    return match.group(1).strip()


def test_it_installs_per_user_with_no_administrator():
    assert _setting("PrivilegesRequired") == "lowest"


def test_it_installs_where_mikes_own_installer_does():
    """Same folder as installer/core.py, so running it over a 1.1.0 install
    replaces it in place rather than leaving two copies."""
    from pathlib import PureWindowsPath

    from installer import core

    # Windows semantics on purpose: the script's backslashes are one path on
    # Windows, but a single odd filename if this runs on a Mac.
    expected = PureWindowsPath(*core.INSTALL_DIR.parts[-2:])          # Programs\Mike
    declared = PureWindowsPath(_setting("DefaultDirName").replace("{localappdata}\\", ""))
    assert declared == expected


def test_the_uninstaller_is_outside_the_folder_updates_replace():
    """In-app updates swap the whole install folder by renaming it. An
    uninstaller inside it would be gone after the first update."""
    app = _setting("DefaultDirName")
    uninstall = _setting("UninstallFilesDir")
    assert uninstall != app and not uninstall.startswith(app + "\\")


#: The AppId the published 1.1.1 Setup.exe uses. It is how Windows knows "the
#: same Mike", so changing it would give everyone who installed 1.1.1 a second
#: entry in Apps & features after upgrading.
SHIPPED_APP_ID = "6F3B2C1A-8D54-4E0B-9A77-4D2C5B8E1F30"


def test_the_app_id_is_the_one_that_shipped_and_matches_what_ci_checks():
    guid = re.search(r"^AppId=\{\{([0-9A-F-]{36})\}?", ISS, re.M)
    assert guid, "AppId must be a GUID"
    assert guid.group(1) == SHIPPED_APP_ID, "the AppId shipped in 1.1.1 must never change"
    assert guid.group(1) in WORKFLOW, (
        "the smoke test looks for the Apps & features entry by this GUID")


def test_it_packages_what_the_build_produces():
    assert "..\\dist\\Mike\\*" in ISS
    assert "packaging\\mike.iss" in WORKFLOW
    assert "Mike-Setup-" in WORKFLOW


def test_the_version_comes_from_the_one_source_not_a_copy():
    assert "AppVersion" in ISS and "config.settings import VERSION" in WORKFLOW
    assert not re.search(r'#define AppVersion "(?!0\.0\.0)', ISS), (
        "the version is passed in by CI; a hand-written one will drift")


def test_an_update_swap_carries_a_1_1_1_uninstaller_across(tmp_path):
    """The 1.1.1 Setup.exe keeps unins000.exe INSIDE the program folder, and
    the in-app updater replaces that whole folder. Without carrying it across,
    the first update leaves a dead entry in Apps & features."""
    from installer import core

    new_files = tmp_path / "unpacked" / "Mike"
    new_files.mkdir(parents=True)
    (new_files / "Mike.exe").write_text("new")

    target = tmp_path / "Programs" / "Mike"
    target.mkdir(parents=True)
    (target / "Mike.exe").write_text("old")
    (target / "unins000.exe").write_text("uninstaller")
    (target / "unins000.dat").write_text("uninstall data")

    core.copy_tree(new_files, target, lambda *_: None)

    assert (target / "Mike.exe").read_text() == "new", "the new version is in place"
    assert (target / "unins000.exe").read_text() == "uninstaller"
    assert (target / "unins000.dat").read_text() == "uninstall data"
    assert not (tmp_path / "Programs" / "Mike.old").exists()
