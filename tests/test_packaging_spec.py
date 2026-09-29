"""The frozen app must ship the same tools as source.

ToolRegistry discovers tools by walking the tools package at runtime, which
PyInstaller's static import graph cannot see. Measured in the installed app
before this was fixed: open_application failed with "Unknown tool: system" on
every call, because tools.system was simply not in the package.
"""
from pathlib import Path

SPEC = Path(__file__).resolve().parent.parent / "packaging" / "mike.spec"


def test_spec_collects_every_runtime_discovered_tool():
    assert 'collect_submodules("tools")' in SPEC.read_text(encoding="utf-8")
