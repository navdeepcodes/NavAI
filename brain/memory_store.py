"""Mike's persistent memory — SQLite V1."""
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

VALID_CATEGORIES = frozenset({
    "preference", "person", "project",
    "location", "workflow", "fact",
})


def _connect() -> sqlite3.Connection:
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), timeout=5, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            content    TEXT    NOT NULL,
            category   TEXT    NOT NULL DEFAULT 'fact',
            created_at REAL    NOT NULL,
            updated_at REAL    NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_memories_category
        ON memories(category)
    """)
    _migrate_project_scoped(conn)
    conn.commit()
    return conn


def _migrate_project_scoped(conn: sqlite3.Connection) -> None:
    """A plain nullable column — existing memories stay global (NULL)."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(memories)")]
    if "project_id" not in cols:
        conn.execute("ALTER TABLE memories ADD COLUMN project_id INTEGER")


_conn: sqlite3.Connection | None = None


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = _connect()
    return _conn


def remember(
    content: str, category: str = "fact", project_id: int | None = None
) -> dict[str, Any]:
    if not content or not content.strip():
        return {"status": "error", "error": "Empty memory content."}

    category = category.strip().lower()
    if category not in VALID_CATEGORIES:
        category = "fact"

    content = content.strip()
    now = time.time()

    # Scoped to the same project — a project-specific "you prefer X" and a
    # different global "you prefer X" shouldn't silently overwrite each other.
    existing = _find_similar(content, category, project_id)
    if existing:
        _db().execute(
            "UPDATE memories SET content = ?, updated_at = ? WHERE id = ?",
            (content, now, existing["id"]),
        )
        _db().commit()
        return {
            "status": "success",
            "result": f"Updated existing memory (id={existing['id']}).",
            "action": "updated",
        }

    _db().execute(
        "INSERT INTO memories (content, category, created_at, updated_at, project_id) "
        "VALUES (?, ?, ?, ?, ?)",
        (content, category, now, now, project_id),
    )
    _db().commit()
    return {
        "status": "success",
        "result": "Memory saved.",
        "action": "created",
    }


def recall(
    query: str = "", category: str = "", project_id: int | None = None
) -> dict[str, Any]:
    query = query.strip()
    category = category.strip().lower()

    conditions = []
    params: list[Any] = []

    if category and category in VALID_CATEGORIES:
        conditions.append("category = ?")
        params.append(category)

    if query:
        keywords = query.split()
        for kw in keywords:
            conditions.append("content LIKE ?")
            params.append(f"%{kw}%")

    # Always scoped, project_id=None included: "no project attached" means
    # global-only, not "ignore scoping entirely" — otherwise a memory saved
    # inside one project would leak into a completely unrelated context the
    # moment no project happens to be open, which defeats the point of
    # scoping it in the first place. Inclusive the other direction though —
    # inside a real project, Mike still sees global facts (your hardware,
    # your general preferences) alongside whatever's project-specific.
    if project_id is not None:
        conditions.append("(project_id = ? OR project_id IS NULL)")
        params.append(project_id)
    else:
        conditions.append("project_id IS NULL")

    where = " AND ".join(conditions) if conditions else "1=1"
    sql = f"SELECT * FROM memories WHERE {where} ORDER BY updated_at DESC LIMIT 20"

    rows = _db().execute(sql, params).fetchall()

    if not rows:
        if not query and not category:
            return {"status": "success", "result": "No memories stored yet.", "memories": []}
        return {"status": "success", "result": "No matching memories found.", "memories": []}

    memories = [
        {"id": r["id"], "content": r["content"], "category": r["category"]}
        for r in rows
    ]
    # Every other tool reports what happened under "result", and the runtime's
    # activity log reads that key. Returning only "memories" meant a
    # successful recall was logged as "Done" while the empty and no-match
    # cases -- which do set "result" -- were described properly. The data
    # still reached the model through the full tool payload, so this was a
    # reporting inconsistency rather than a lost recall, but anything reading
    # the documented key saw nothing.
    summary = "; ".join(m["content"] for m in memories[:5])
    if len(memories) > 5:
        summary += f" (and {len(memories) - 5} more)"
    return {
        "status": "success",
        "memories": memories,
        "result": f"Recalled {len(memories)} memory(s): {summary}",
    }


class ForgetSelection:
    """The exact set of memories a forget request names.

    Confirmation and deletion both read this, so the list the user is shown
    is built by the same code that decides what gets removed. A preview
    computed by separate logic could describe one set and delete another,
    which is the failure mode a confirmation exists to prevent.
    """

    __slots__ = ("where", "params", "scope", "error")

    def __init__(self, where: str = "", params: list | None = None,
                 scope: str = "", error: str = ""):
        self.where = where
        self.params = params or []
        self.scope = scope
        self.error = error

    @property
    def valid(self) -> bool:
        return not self.error

    def rows(self) -> list[dict[str, Any]]:
        if not self.valid:
            return []
        return [
            dict(r) for r in _db().execute(
                f"SELECT id, content, category FROM memories WHERE {self.where} "
                "ORDER BY updated_at DESC",
                self.params,
            ).fetchall()
        ]


def forget_selection(query: str = "", memory_id: int | None = None) -> ForgetSelection:
    """Resolve a forget request to a selector, without touching anything."""
    if memory_id is not None:
        return ForgetSelection("id = ?", [memory_id], f"memory {memory_id}")

    query = (query or "").strip()

    if query.lower() in ("everything", "all", "all memories"):
        return ForgetSelection("1=1", [], "every stored memory")

    if not query:
        return ForgetSelection(error="Provide a query or memory_id to forget.")

    keywords = query.split()
    where = " AND ".join("content LIKE ?" for _ in keywords)
    return ForgetSelection(where, [f"%{kw}%" for kw in keywords],
                           f"memories matching {query!r}")


def preview_forget(query: str = "", memory_id: int | None = None) -> dict[str, Any]:
    """What a forget call would remove. Reads only."""
    selection = forget_selection(query, memory_id)
    if not selection.valid:
        return {"status": "error", "error": selection.error, "memories": []}
    rows = selection.rows()
    return {"status": "success", "scope": selection.scope, "memories": rows}


def forget(query: str = "", memory_id: int | None = None) -> dict[str, Any]:
    selection = forget_selection(query, memory_id)
    if not selection.valid:
        return {"status": "error", "error": selection.error}

    # Read the doomed rows before deleting them, so the result can name what
    # went rather than only how many.
    doomed = selection.rows()

    if not doomed:
        if memory_id is not None:
            return {"status": "error", "error": f"No memory with id {memory_id}."}
        return {"status": "success", "result": "No matching memories to forget.",
                "deleted": 0}

    _db().execute(f"DELETE FROM memories WHERE {selection.where}", selection.params)
    _db().commit()

    # Independent verification: re-run the same selector against the database
    # and require it to come back empty. rowcount is the driver's own report
    # of its work; this reads the stored state instead.
    survivors = selection.rows()
    if survivors:
        return {
            "status": "error",
            "error": (
                f"Tried to forget {len(doomed)} memory(s) but {len(survivors)} "
                "still exist afterwards. Nothing should be assumed deleted."
            ),
        }

    gone = "; ".join(m["content"][:60] for m in doomed[:5])
    if len(doomed) > 5:
        gone += f" (and {len(doomed) - 5} more)"
    return {
        "status": "success",
        "result": f"Forgot {len(doomed)} memory(s), verified gone: {gone}",
        "deleted": len(doomed),
    }


def auto_recall(message: str, project_id: int | None = None) -> list[dict]:
    """Fast keyword search for automatic context injection."""
    words = message.lower().split()
    stop = {"the", "a", "an", "is", "are", "was", "were", "what", "where",
            "when", "who", "how", "do", "does", "did", "my", "me", "i",
            "you", "your", "can", "could", "would", "should", "will",
            "to", "in", "on", "at", "for", "of", "and", "or", "it",
            "that", "this", "with", "from", "about", "have", "has"}
    keywords = [w for w in words if len(w) > 2 and w not in stop]

    if not keywords:
        return []

    conditions = ["LOWER(content) LIKE ?" for _ in keywords]
    params: list[Any] = [f"%{kw}%" for kw in keywords]
    where = " OR ".join(conditions)

    if project_id is not None:
        where = f"({where}) AND (project_id = ? OR project_id IS NULL)"
        params.append(project_id)

    rows = _db().execute(
        f"SELECT DISTINCT content, category FROM memories WHERE {where} "
        "ORDER BY updated_at DESC LIMIT 5",
        params,
    ).fetchall()

    return [{"content": r["content"], "category": r["category"]} for r in rows]


def _find_similar(
    content: str, category: str, project_id: int | None = None
) -> dict | None:
    """Find an existing memory that's similar enough to update."""
    stop = {"the", "a", "an", "is", "are", "in", "on", "at", "to", "for",
            "of", "and", "or", "my", "i", "that", "this", "it", "with",
            "from", "about", "have", "has", "was", "were", "be", "been"}
    words = [w for w in content.lower().split() if w not in stop and len(w) > 2]

    if not words:
        return None

    if project_id is None:
        rows = _db().execute(
            "SELECT * FROM memories WHERE category = ? AND project_id IS NULL "
            "ORDER BY updated_at DESC",
            (category,),
        ).fetchall()
    else:
        rows = _db().execute(
            "SELECT * FROM memories WHERE category = ? AND project_id = ? "
            "ORDER BY updated_at DESC",
            (category, project_id),
        ).fetchall()

    for row in rows:
        row_words = set(row["content"].lower().split())
        matching = sum(1 for w in words if w in row_words)
        if matching >= max(2, len(words) // 2):
            return dict(row)

    return None


def db_path() -> str:
    return str(_DB_PATH)


def all_memories(limit: int = 500) -> list[dict[str, Any]]:
    """
    Every memory, newest first — for a UI that shows the whole list rather
    than a tool searching for something specific. recall() is capped at 20
    and built for the model's own lookups; this is the same table, no cap
    that matters in practice, meant for a person reading the full list.
    """
    rows = _db().execute(
        "SELECT id, content, category, created_at, updated_at "
        "FROM memories ORDER BY updated_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]
