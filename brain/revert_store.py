"""Before-state capture and revert for file changes — the smallest thing
that lets a bad write or delete be undone, not a version-control system.

Only text files are snapshotted (a revert that silently mangled a binary
would be worse than no revert at all). Folders aren't snapshotted either —
a folder's "previous state" isn't a single blob worth capturing cheaply.

Linkage to an Activity row is soft, not a hard foreign key: the snapshot is
captured deep inside the tool call, before the actual write/delete, which
has no access to the Activity row id that only exists up in the UI layer.
attach_to_activity() closes that gap right after the tool call returns, by
claiming the most recently captured orphan — safe because tools run one at
a time, and time-windowed so a stale orphan from an earlier, unrelated
action can never be misattached to a new one.
"""
from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import Any

# MIKE_DATA_DIR overrides the real per-user data directory — set by
# tests/_isolate.py (or a pytest fixture) so tests can never touch the
# production database. Unset in normal app runs.
_DB_DIR = Path(os.environ["MIKE_DATA_DIR"]) if os.environ.get("MIKE_DATA_DIR") \
    else Path.home() / "Library" / "Application Support" / "Mike"
_DB_PATH = _DB_DIR / "memory.db"

# Generous enough for a slow write, tight enough that an old orphaned
# snapshot from an unrelated turn can never attach to a new activity row.
_ATTACH_WINDOW_SECONDS = 30

# Above this, don't bother snapshotting — a revert store isn't meant to
# become a second copy of every large file Mike ever touches.
_MAX_SNAPSHOT_BYTES = 2_000_000


def _connect() -> sqlite3.Connection:
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), timeout=5, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS snapshots (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_id      INTEGER,
            path             TEXT    NOT NULL,
            existed          INTEGER NOT NULL,
            previous_content TEXT,
            created_at       REAL    NOT NULL
        )
        """
    )
    conn.commit()
    return conn


_conn: sqlite3.Connection | None = None


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = _connect()
    return _conn


def capture(path: str) -> int | None:
    """
    Called right before a write or delete actually touches disk. Returns the
    snapshot id, or None if there's nothing sensible to capture (a folder, a
    file too large, or one that isn't valid text) — in which case there's
    simply no revert available for whatever's about to happen, which is
    always safe to report as absent rather than guessed at.
    """
    try:
        resolved = Path(path).expanduser().resolve()
    except Exception:
        return None

    existed = resolved.is_file()
    previous_content: str | None = None

    if existed:
        try:
            if resolved.stat().st_size > _MAX_SNAPSHOT_BYTES:
                return None
            previous_content = resolved.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return None
    elif resolved.exists():
        # Exists but isn't a plain file (a directory) — not snapshotted.
        return None

    cur = _db().execute(
        "INSERT INTO snapshots (activity_id, path, existed, previous_content, created_at) "
        "VALUES (NULL, ?, ?, ?, ?)",
        (str(resolved), 1 if existed else 0, previous_content, time.time()),
    )
    _db().commit()
    return cur.lastrowid


def attach_to_activity(activity_id: int) -> None:
    """
    Claims the most recently captured still-orphaned snapshot for this
    activity row — called right after the tool call that may have captured
    one has finished. A no-op if nothing was captured (capture() returned
    None) or if the orphan is older than the attach window.
    """
    cutoff = time.time() - _ATTACH_WINDOW_SECONDS
    _db().execute(
        """
        UPDATE snapshots SET activity_id = ?
        WHERE id = (
            SELECT id FROM snapshots
            WHERE activity_id IS NULL AND created_at >= ?
            ORDER BY created_at DESC LIMIT 1
        )
        """,
        (activity_id, cutoff),
    )
    _db().commit()


def for_activity(activity_id: int) -> dict[str, Any] | None:
    row = _db().execute(
        "SELECT * FROM snapshots WHERE activity_id = ?", (activity_id,)
    ).fetchone()
    return dict(row) if row else None


def revert(snapshot_id: int) -> dict[str, Any]:
    """
    Restores the file to what it was before the write, or removes it if it
    didn't exist before (an undo for a create, not just an edit).
    """
    row = _db().execute(
        "SELECT * FROM snapshots WHERE id = ?", (snapshot_id,)
    ).fetchone()
    if row is None:
        return {"status": "error", "error": "That snapshot no longer exists."}

    path = Path(row["path"])

    # A revert is itself a write or delete to disk, same as the tool calls
    # that create these snapshots in the first place — so it gets the same
    # safety net. Without this, reverting was a one-way door: if the file
    # had changed again since the original snapshot (the user's own later
    # edit, or a later unrelated write), that state was simply discarded
    # with no way back. Now a revert is itself always one more revert away.
    capture(str(path))

    try:
        if row["existed"]:
            path.write_text(row["previous_content"] or "", encoding="utf-8")
            return {"status": "success", "result": f"Restored {path.name} to what it was before."}
        else:
            if path.exists():
                path.unlink()
            return {"status": "success", "result": f"Removed {path.name} — it didn't exist before this."}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
