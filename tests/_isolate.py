"""Import this FIRST, before any `brain` or `config` import, in any test that
touches persistent Mike state (memory, activity, situation, projects, revert
snapshots, preferences).

Redirects every store's data directory to a throwaway temp folder for the
lifetime of this process by setting MIKE_DATA_DIR before those modules
compute their on-disk paths (they read it once, at import time). Without
this, tests run against the real ~/Library/Application Support/Mike and can
destroy real user data — which is exactly what happened once already.

pytest runs get this automatically from tests/conftest.py. This module
exists for the other way these tests get run: a bare
`python tests/test_whatever.py`, which never loads conftest.py.
"""
from __future__ import annotations

import os
import tempfile

if "MIKE_DATA_DIR" not in os.environ:
    os.environ["MIKE_DATA_DIR"] = tempfile.mkdtemp(prefix="mike-test-")

DATA_DIR = os.environ["MIKE_DATA_DIR"]
