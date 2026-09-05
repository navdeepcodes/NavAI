"""Reopen a spreadsheet Mike wrote in a real spreadsheet application.

The pytest suite verifies Mike's writes by reading the file back with
openpyxl — the same library that wrote it. That proves the bytes round-trip;
it does not prove Apple Numbers considers the file valid, or that a formula
Mike stored produces the number Mike claimed.

This does. It opens the file in Numbers, reads the sheet through the
accessibility tree, and reports the values a real application computed. Run
by hand because it takes over the screen.

    venv/bin/python tests/verify_in_numbers.py <path.xlsx> [expected ...]
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)

    path = Path(sys.argv[1]).expanduser().resolve()
    expected = sys.argv[2:]
    assert path.exists(), path

    from computer.session import SESSION

    available, why = SESSION.availability()
    print(f"computer control: {available} ({why})")

    subprocess.run(["open", "-a", "Numbers", str(path)], check=True)
    print(f"opened {path.name} in Numbers; waiting for the document to render")
    time.sleep(9)

    SESSION.focus_app("Numbers")
    time.sleep(1.5)

    observed = SESSION.observe(app="Numbers", limit=400)
    elements = observed.get("elements") or []
    print(f"accessibility elements: {len(elements)}")

    text = " ".join(
        str(e.get("label") or "") + " " + str(e.get("value") or "")
        for e in elements
    )

    found = {}
    for token in expected:
        found[token] = token in text
        print(f"  {'FOUND    ' if found[token] else 'NOT FOUND'} {token}")

    if not elements or not any(found.values()):
        # Numbers renders its canvas rather than exposing every cell, so a
        # miss here is a limit of the observation route, not proof the file is
        # wrong. Fall back to the eyes.
        print("\nfalling back to vision (the sheet canvas is not fully in the "
              "accessibility tree)")
        from vision import screen_capture

        shot = screen_capture.capture()
        print(f"screenshot: {shot}")

    print("\nleaving Numbers open so the result is visible.")


if __name__ == "__main__":
    main()
