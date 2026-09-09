"""A durable record of actions Mike actually performed.

Written only when a tool genuinely ran, and only from its real result — this
is a log of what happened, never of what was intended. Lives in the same local
database as everything else.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from typing import Any

from hostplatform import storage
from logs.logger import logger

# MIKE_DATA_DIR overrides the real per-user data directory — set by
# tests/_isolate.py (or a pytest fixture) so tests can never touch the
# production database. Unset in normal app runs.
_DB_DIR = storage.data_dir()
_DB_PATH = _DB_DIR / "memory.db"

MAX_ROWS = 500


def _connect() -> sqlite3.Connection:
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    # A shared connection reached from several threads (the UI thread,
    # a worker thread, a cancelled turn's cleanup) needs its statements
    # serialized -- a bare sqlite3.Connection has no lock of its own, and
    # concurrent execute()/commit() calls on one raced into "database is
    # locked" or, once, a hang. See brain/_local_db.py.
    from brain._local_db import connect as _locked_connect
    conn = _locked_connect(str(_DB_PATH))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS activity (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            action     TEXT    NOT NULL,
            outcome    TEXT    NOT NULL DEFAULT '',
            succeeded  INTEGER NOT NULL DEFAULT 1,
            started_at REAL    NOT NULL
        )
        """
    )
    _migrate_project_scoped(conn)
    conn.commit()
    return conn


def _migrate_project_scoped(conn: sqlite3.Connection) -> None:
    cols = [r[1] for r in conn.execute("PRAGMA table_info(activity)")]
    if "project_id" not in cols:
        conn.execute("ALTER TABLE activity ADD COLUMN project_id INTEGER")


_conn: sqlite3.Connection | None = None
# Guards the check-then-set below. Two threads calling _db() at the same
# moment could otherwise both see _conn as None, both open a connection,
# and both run CREATE TABLE against the same file at once -- measured:
# that race is what "database is locked" actually came from under real
# concurrency, not the execute/commit calls that ran afterwards.
_conn_lock = threading.Lock()


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        with _conn_lock:
            if _conn is None:
                _conn = _connect()
    return _conn


def begin(action: str, project_id: int | None = None) -> int | None:
    """Record that an action started. Returns its row id."""

    if not action or not action.strip():
        return None
    try:
        cur = _db().execute(
            "INSERT INTO activity (action, started_at, project_id) VALUES (?, ?, ?)",
            (action.strip(), time.time(), project_id),
        )
        _db().commit()
        return cur.lastrowid
    except Exception:
        logger.exception("Could not record activity start for %r.", action)
        return None


def complete(row_id: int | None, outcome: str, succeeded: bool = True) -> None:
    """Close out an action with the result the tool actually returned."""

    if row_id is None:
        return
    try:
        _db().execute(
            "UPDATE activity SET outcome = ?, succeeded = ? WHERE id = ?",
            ((outcome or "").strip()[:400], 1 if succeeded else 0, row_id),
        )
        _db().commit()
        _trim()
    except Exception:
        logger.exception("Could not record the outcome of activity %r.", row_id)


def get(row_id: int | None) -> dict[str, Any] | None:
    """One row, by id.

    The store could previously only answer "the most recent N", which is the
    right question for a list the user reads and the wrong one for "what
    became of this particular action" — the question the finalization path
    and its tests actually ask. Scanning a recent window for a known id looks
    equivalent and is not: anything that inserts rows afterwards pushes the
    row out of the window, and the lookup fails for a row that is present and
    correct. That is exactly how it failed, intermittently, in the
    real-application suite where background workers are still writing.
    """
    if row_id is None:
        return None
    try:
        row = _db().execute(
            "SELECT id, action, outcome, succeeded, started_at "
            "FROM activity WHERE id = ?",
            (row_id,),
        ).fetchone()
        return dict(row) if row else None
    except Exception:
        logger.exception("Could not look up activity %r.", row_id)
        return None


def recent(limit: int = 60) -> list[dict[str, Any]]:
    try:
        rows = _db().execute(
            # id breaks ties. started_at is a float and collisions are rare,
            # but "rare" in an ordering is a bug that surfaces as rows
            # swapping places for no reason the user can see.
            "SELECT id, action, outcome, succeeded, started_at "
            "FROM activity ORDER BY started_at DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        logger.exception("Could not list recent activity.")
        return []


def clear() -> None:
    try:
        _db().execute("DELETE FROM activity")
        _db().commit()
    except Exception:
        logger.exception("Could not clear activity history.")


def _trim() -> None:
    try:
        _db().execute(
            "DELETE FROM activity WHERE id NOT IN "
            "(SELECT id FROM activity ORDER BY started_at DESC LIMIT ?)",
            (MAX_ROWS,),
        )
        _db().commit()
    except Exception:
        pass
