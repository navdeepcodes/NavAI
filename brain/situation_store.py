from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

# MIKE_DATA_DIR overrides the real per-user data directory — set by
# tests/_isolate.py (or a pytest fixture) so tests can never touch the
# production database. Unset in normal app runs.
_DB_DIR = Path(os.environ["MIKE_DATA_DIR"]) if os.environ.get("MIKE_DATA_DIR") \
    else Path.home() / "Library" / "Application Support" / "Mike"
_DB_PATH = _DB_DIR / "memory.db"


def _connect() -> sqlite3.Connection:
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), timeout=5, check_same_thread=False)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS situation (
            id         INTEGER PRIMARY KEY CHECK (id = 1),
            summary    TEXT    NOT NULL,
            updated_at REAL    NOT NULL
        )
        """
    )
    _migrate_project_scoped(conn)
    conn.commit()
    return conn


def _migrate_project_scoped(conn: sqlite3.Connection) -> None:
    """
    The original table held exactly one global row (id=1, enforced by a
    CHECK constraint). Project-scoped continuity needs one row per project
    plus the global one — SQLite can't drop a CHECK constraint with ALTER,
    so this rebuilds the table once, carrying the old row forward as the
    global (project_id IS NULL) row. A no-op after the first launch that
    runs it.
    """
    cols = [r[1] for r in conn.execute("PRAGMA table_info(situation)")]
    if "project_id" in cols:
        return

    old_row = conn.execute(
        "SELECT summary, updated_at FROM situation WHERE id = 1"
    ).fetchone()

    conn.execute("ALTER TABLE situation RENAME TO situation_v1")
    conn.execute(
        """
        CREATE TABLE situation (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            summary    TEXT    NOT NULL,
            updated_at REAL    NOT NULL
        )
        """
    )
    # Enforces at most one row per real project. Deliberately not applied to
    # the global row (project_id IS NULL) — SQLite excludes NULLs from a
    # unique index by default, so uniqueness there is kept by load()/save()
    # always checking "WHERE project_id IS NULL" before inserting, the same
    # pattern the rest of this file's callers already rely on.
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_situation_project "
        "ON situation(project_id) WHERE project_id IS NOT NULL"
    )

    if old_row and old_row[0]:
        conn.execute(
            "INSERT INTO situation (project_id, summary, updated_at) VALUES (NULL, ?, ?)",
            (old_row[0], old_row[1]),
        )

    conn.execute("DROP TABLE situation_v1")


_conn: sqlite3.Connection | None = None


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = _connect()
    return _conn


def load(project_id: int | None = None) -> str:
    if project_id is None:
        row = _db().execute(
            "SELECT summary FROM situation WHERE project_id IS NULL"
        ).fetchone()
    else:
        row = _db().execute(
            "SELECT summary FROM situation WHERE project_id = ?", (project_id,)
        ).fetchone()

    return row[0] if row else ""


def save(summary: str, project_id: int | None = None) -> None:
    if project_id is None:
        existing = _db().execute(
            "SELECT id FROM situation WHERE project_id IS NULL"
        ).fetchone()
    else:
        existing = _db().execute(
            "SELECT id FROM situation WHERE project_id = ?", (project_id,)
        ).fetchone()

    now = time.time()

    if existing:
        _db().execute(
            "UPDATE situation SET summary = ?, updated_at = ? WHERE id = ?",
            (summary, now, existing[0]),
        )
    else:
        _db().execute(
            "INSERT INTO situation (project_id, summary, updated_at) VALUES (?, ?, ?)",
            (project_id, summary, now),
        )

    _db().commit()
