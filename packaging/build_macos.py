"""Build Mike.app for macOS and prove it has all its tools.

    python packaging/build_macos.py [output_dir]      (default: ./dist)

Run it from the venv that has the requirements and PyInstaller installed --
PyInstaller only bundles what it can import. After building it launches the
*built* app with --self-check, which loads the real tool registry with no
window and no model, and fails the build if any tool is missing. That is the
check that would have caught two releases that started normally but could not
search the web or open an app.

Unsigned and not notarised, like the first macOS release; see the Gatekeeper
notes in README.md.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC = Path(__file__).resolve().parent / "mike_macos.spec"


def main() -> None:
    out = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else REPO_ROOT / "dist"
    print(f"-> Building Mike.app into {out} ...")
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--distpath", str(out),
         "--workpath", str(REPO_ROOT / "build"), str(SPEC)],
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        sys.exit(f"PyInstaller failed with exit code {result.returncode}")

    binary = out / "Mike.app" / "Contents" / "MacOS" / "Mike"
    if not binary.is_file():
        sys.exit(f"Expected {binary} after the build; it is not there.")

    print("-> Self-check: does the built app have all its tools?")
    with tempfile.TemporaryDirectory() as data_dir:
        report_path = Path(data_dir) / "report.json"
        env = {"MIKE_DATA_DIR": data_dir, "PATH": "/usr/bin:/bin"}
        check = subprocess.run([str(binary), "--self-check", str(report_path)], env=env)
        report = json.loads(report_path.read_text()) if report_path.exists() else {}
    if check.returncode != 0 or not report.get("ok"):
        sys.exit(f"Self-check FAILED: missing={report.get('missing')} error={report.get('error')}")
    print(f"   OK: {', '.join(report['tools'])}")
    print(f"\nBuilt and verified {out / 'Mike.app'}")


if __name__ == "__main__":
    main()
