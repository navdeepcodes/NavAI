"""`Mike --self-check` must fail loudly when a build is missing a tool.

The release process runs it on the *built* app. A check that always passes is
worse than none, so the failing cases are tested as hard as the passing one.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401


def test_a_complete_build_passes_and_reports_its_tools(tmp_path):
    from brain import self_check

    out = tmp_path / "report.json"
    assert self_check.run([str(out)]) == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["ok"] is True and report["missing"] == [] and report["error"] is None
    assert set(self_check.EXPECTED_TOOLS) <= set(report["tools"])


def test_a_build_missing_a_tool_fails(tmp_path, monkeypatch):
    """The real failure: a tool package that never got bundled."""
    from brain import self_check

    monkeypatch.setattr(self_check, "EXPECTED_TOOLS",
                        self_check.EXPECTED_TOOLS | {"a_tool_nobody_shipped"})
    out = tmp_path / "report.json"
    assert self_check.run([str(out)]) == 1
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["ok"] is False and report["missing"] == ["a_tool_nobody_shipped"]


def test_a_registry_that_cannot_load_fails_instead_of_crashing(tmp_path, monkeypatch):
    import tools.tool_registry as registry

    from brain import self_check

    def boom(*_a, **_k):
        raise RuntimeError("registry exploded")

    monkeypatch.setattr(registry, "ToolRegistry", boom)
    out = tmp_path / "report.json"
    assert self_check.run([str(out)]) == 1
    assert "registry exploded" in json.loads(out.read_text(encoding="utf-8"))["error"]


def test_it_works_with_no_console_and_no_path(monkeypatch, capsys):
    """A windowed Windows build has no stdout; the path is optional."""
    from brain import self_check

    monkeypatch.setattr(sys, "stdout", None)
    assert self_check.run([]) == 0


def test_the_expected_tools_match_the_tool_packages_in_the_repo():
    """Add a tool package and forget to list it here, and a build without it
    would still pass. Every tools/<name>/ that defines a *_tool.py must be
    expected."""
    from pathlib import Path

    from brain import self_check

    root = Path(__file__).resolve().parent.parent / "tools"
    packages = {p.name for p in root.iterdir()
                if p.is_dir() and any(p.glob("*_tool.py")) and p.name != "permissions"}
    assert packages <= set(self_check.EXPECTED_TOOLS), (
        f"tool packages not in EXPECTED_TOOLS: {sorted(packages - set(self_check.EXPECTED_TOOLS))}")
