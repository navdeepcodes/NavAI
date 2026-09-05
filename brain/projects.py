"""Projects — a name for a place, not a new place to manage.

The smallest thing that lets Mike's continuity differ per piece of work: a
row keyed by an absolute path, auto-created the first time it's seen and
touched every time it's seen again. Nobody creates a project by hand — it's
resolved from the one reliable "which root am I in" signal that already
exists (the IDE bridge's workspace_root). No UI, no picker, no manual
project management: this exists so situation/memory/activity can be tagged
by it, nothing more.
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


def _connect() -> sqlite3.Connection:
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), timeout=5, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            root_path      TEXT    NOT NULL UNIQUE,
            name           TEXT    NOT NULL,
            created_at     REAL    NOT NULL,
            last_active_at REAL    NOT NULL
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


def resolve(root_path: str) -> int | None:
    """
    Find-or-create the project for this root path and mark it as the one
    just seen. Returns None only if root_path is empty — every real path
    always resolves to a real, stable id.
    """
    if not root_path or not root_path.strip():
        return None

    normalized = str(Path(root_path.strip()).expanduser())
    now = time.time()

    existing = _db().execute(
        "SELECT id FROM projects WHERE root_path = ?", (normalized,)
    ).fetchone()

    if existing:
        _db().execute(
            "UPDATE projects SET last_active_at = ? WHERE id = ?",
            (now, existing["id"]),
        )
        _db().commit()
        return existing["id"]

    name = Path(normalized).name or normalized
    cur = _db().execute(
        "INSERT INTO projects (root_path, name, created_at, last_active_at) "
        "VALUES (?, ?, ?, ?)",
        (normalized, name, now, now),
    )
    _db().commit()
    return cur.lastrowid


def get(project_id: int) -> dict[str, Any] | None:
    row = _db().execute(
        "SELECT * FROM projects WHERE id = ?", (project_id,)
    ).fetchone()
    return dict(row) if row else None


def recent(limit: int = 20) -> list[dict[str, Any]]:
    rows = _db().execute(
        "SELECT * FROM projects ORDER BY last_active_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def current() -> int | None:
    """
    The project for whatever IDE workspace is attached right now, or None
    for "no project" (the global scope). The only signal used for this is
    the IDE bridge's workspace_root — deliberately not frontmost-app
    detection, which gives an app name, not a root path to key anything on.

    Callable from either the runtime (to scope situation/memory) or the UI
    (to tag an activity row) without either needing to know about the other.
    """
    try:
        from ide import manager as ide_manager
        if ide_manager.is_connected():
            root = ide_manager.get_context().workspace_root
            if root:
                return resolve(root)
    except Exception:
        pass
    return None
