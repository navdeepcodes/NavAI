"""Build the Windows release artifact: dist/Mike-windows-<version>.zip.

    python packaging/build_windows.py

Run from the venv this repo already uses (the one with PySide6, comtypes,
faster-whisper, pywin32 installed) -- PyInstaller only bundles what it finds
importable in the interpreter that runs it.

What this does, and why each step exists:

1. Pre-generates the comtypes UI Automation bindings. computer/windows.py
   normally has comtypes read a type library and write Python into
   comtypes/gen the first time UI Automation is used -- that write does not
   happen in a frozen app (comtypes disables its own codegen when
   sys.frozen is set, and the install directory may not be writable
   anyway). Generating them now means they ship as ordinary bundled
   modules instead of silently going missing on a user's machine.
2. Runs PyInstaller against mike.spec.
3. Zips dist/Mike/ into dist/Mike-windows-<version>.zip -- the exact
   filename the website's download button already links to, matching the
   macOS release's own Mike-macOS-<version>.zip naming.

Does not touch code signing. The current release (and the macOS one before
it) ships unsigned with explicit SmartScreen/Gatekeeper bypass instructions;
that is a deliberate, disclosed early-access tradeoff, not an oversight this
script should paper over.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGING_DIR = Path(__file__).resolve().parent
DIST_DIR = REPO_ROOT / "dist"


def _version() -> str:
    sys.path.insert(0, str(REPO_ROOT))
    from config.settings import VERSION
    return VERSION


def _pregenerate_comtypes() -> None:
    print("-> Pre-generating comtypes UI Automation bindings...")
    import comtypes.client as cc

    cc.GetModule("UIAutomationCore.dll")
    print("  done.")


def _run_pyinstaller() -> None:
    print("-> Running PyInstaller...")
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm",
         str(PACKAGING_DIR / "mike.spec")],
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        sys.exit(f"PyInstaller failed with exit code {result.returncode}")


def _zip_release(version: str) -> Path:
    built = DIST_DIR / "Mike"
    if not built.is_dir():
        sys.exit(f"Expected PyInstaller output at {built}, but it doesn't exist.")
    exe = built / "Mike.exe"
    if not exe.is_file():
        sys.exit(f"Expected {exe} to exist after the build; it doesn't.")

    zip_path = DIST_DIR / f"Mike-windows-{version}.zip"
    if zip_path.exists():
        zip_path.unlink()

    print(f"-> Zipping {built} -> {zip_path.name}...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in built.rglob("*"):
            if path.is_file():
                zf.write(path, arcname=Path("Mike") / path.relative_to(built))

    return zip_path


def main() -> None:
    version = _version()
    print(f"Building Mike {version} for Windows.\n")

    _pregenerate_comtypes()
    # The open-source licences screen lists exactly what this build bundles.
    print("-> Writing open-source licence notices...")
    subprocess.run([sys.executable, str(PACKAGING_DIR / "generate_notices.py")],
                   cwd=REPO_ROOT, check=True)
    _run_pyinstaller()
    zip_path = _zip_release(version)

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"\nBuilt {zip_path} ({size_mb:.1f} MB).")
    print("This filename matches what huddlecode.com's Windows download button")
    print("already links to -- attach it to a GitHub release tagged for Windows.")


if __name__ == "__main__":
    main()
