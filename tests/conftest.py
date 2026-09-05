"""Auto-loaded by pytest before any test module — applies to every file
under tests/, present or future, whether or not that file remembers to
import tests/_isolate.py itself.

Sets MIKE_DATA_DIR to a throwaway temp folder before anything else runs, so
brain/memory_store.py, activity_store.py, situation_store.py, projects.py,
revert_store.py and config/preferences.py all resolve their on-disk paths
under it instead of the real ~/Library/Application Support/Mike.

This only protects `pytest`-driven runs. A test invoked directly with
`python tests/test_whatever.py` bypasses conftest.py entirely, which is why
tests/_isolate.py exists as a second, explicit line of defense for the
handful of tests that touch persistent state.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if "MIKE_DATA_DIR" not in os.environ:
    os.environ["MIKE_DATA_DIR"] = tempfile.mkdtemp(prefix="mike-test-")


# Manual end-to-end scripts, not pytest tests. Their step functions take
# arguments and chain state through a __main__ block (a captured screenshot is
# passed to the model, its description to the next step), which pytest cannot
# drive — it reads those parameters as fixture requests and reports a
# collection error for each one. That produced eight permanent errors in every
# run, which is noise that hides real breakage.
#
# They are still valuable and still run directly:
#     venv/bin/python tests/test_vision_e2e_real.py
#     venv/bin/python tests/test_voice_e2e.py
#
# Nothing here weakens them; it only stops pytest claiming ownership of
# scripts it was never able to execute.
collect_ignore = [
    "test_vision_e2e_real.py",
    "test_voice_e2e.py",
]


# ══ external side effects are blocked by default ═══════════
#
# A test in this suite once called the live Gmail send executor. It guarded
# itself with "skip if credentials work", so it was silent until the day
# authentication started working -- and then every full run sent a real email
# to a@b.com. Ten went out before it was caught.
#
# Detecting that by reading the code was not enough, because the code looked
# reasonable. So the live path is severed for the whole suite instead, and a
# test that genuinely needs it has to say so out loud:
#
#     @pytest.mark.sends_real_email
#     def test_something_that_really_sends(): ...
#
# There are currently no such tests. Real send behaviour is exercised by
# tests/endurance_email.py, which is run deliberately and by hand.

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "sends_real_email: test genuinely transmits mail; excluded from the "
        "default no-side-effects guard",
    )
    config.addinivalue_line(
        "markers",
        "drives_real_apps: test launches and drives real applications; "
        "opt in with MIKE_RUN_APP_E2E=1",
    )


class _BlockedExternalSend(RuntimeError):
    """Raised when a test reaches a live external send path."""


@pytest.fixture(autouse=True)
def _no_real_external_sends(request, monkeypatch):
    """Sever the live mail path unless a test explicitly opts in."""
    if request.node.get_closest_marker("sends_real_email"):
        return

    try:
        from tools.email import gmail_client
    except Exception:
        return

    def refuse(self, *args, **kwargs):
        raise _BlockedExternalSend(
            "This test reached the live Gmail send path. Unit tests must not "
            "transmit mail. Patch the client, or mark the test with "
            "@pytest.mark.sends_real_email if it genuinely must send."
        )

    monkeypatch.setattr(gmail_client.GmailClient, "send_email", refuse, raising=False)


# ══ real-application E2E tests are opt-in ══════════════════
#
# Some tests drive actual applications: they launch TextEdit or VS Code, move
# focus, and synthesise clicks and keystrokes. They are genuinely valuable --
# they are the only thing that proves synthetic input reaches a real interface
# -- but they contend with each other and with whatever else is on the screen,
# so inside a full suite they fail intermittently for reasons that have
# nothing to do with the code under test.
#
# A test that fails a third of the time teaches people to ignore failures, so
# they are excluded by default and run deliberately:
#
#     MIKE_RUN_APP_E2E=1 venv/bin/python -m pytest tests/ -q
#
# The deterministic coverage of the same logic -- identity resolution,
# mutation handling, safety gating -- stays in the default suite via stubbed
# controllers, so nothing about the *logic* is only checked here.

def pytest_collection_modifyitems(config, items):
    import os

    if os.environ.get("MIKE_RUN_APP_E2E"):
        return
    skip = pytest.mark.skip(
        reason="drives real applications; set MIKE_RUN_APP_E2E=1 to run"
    )
    for item in items:
        if item.get_closest_marker("drives_real_apps"):
            item.add_marker(skip)
