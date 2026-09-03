"""Mike's persistent memory — SQLite V1."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

_DB_DIR = Path.home() / "Library" / "Application Support" / "Mike"
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
    conn.commit()
    return conn


_conn: sqlite3.Connection | None = None


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = _connect()
    return _conn


def remember(content: str, category: str = "fact") -> dict[str, Any]:
    if not content or not content.strip():
        return {"status": "error", "error": "Empty memory content."}

    category = category.strip().lower()
    if category not in VALID_CATEGORIES:
        category = "fact"

    content = content.strip()
    now = time.time()

    existing = _find_similar(content, category)
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
        "INSERT INTO memories (content, category, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (content, category, now, now),
    )
    _db().commit()
    return {
        "status": "success",
        "result": "Memory saved.",
        "action": "created",
    }


def recall(query: str = "", category: str = "") -> dict[str, Any]:
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
    return {"status": "success", "memories": memories}


def forget(query: str = "", memory_id: int | None = None) -> dict[str, Any]:
    if memory_id is not None:
        cur = _db().execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        _db().commit()
        if cur.rowcount:
            return {"status": "success", "result": f"Deleted memory {memory_id}."}
        return {"status": "error", "error": f"No memory with id {memory_id}."}

    if query and query.strip().lower() in ("everything", "all", "all memories"):
        cur = _db().execute("DELETE FROM memories")
        _db().commit()
        return {"status": "success", "result": f"Deleted all {cur.rowcount} memories."}

    if not query:
        return {"status": "error", "error": "Provide a query or memory_id to forget."}

    keywords = query.strip().split()
    conditions = [f"content LIKE ?" for kw in keywords]
    params = [f"%{kw}%" for kw in keywords]

    where = " AND ".join(conditions)
    cur = _db().execute(f"DELETE FROM memories WHERE {where}", params)
    _db().commit()

    if cur.rowcount:
        return {"status": "success", "result": f"Forgot {cur.rowcount} matching memory(s)."}
    return {"status": "success", "result": "No matching memories to forget."}


def auto_recall(message: str) -> list[dict]:
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

    conditions = [f"LOWER(content) LIKE ?" for kw in keywords]
    params = [f"%{kw}%" for kw in keywords]
    where = " OR ".join(conditions)

    rows = _db().execute(
        f"SELECT DISTINCT content, category FROM memories WHERE {where} "
        "ORDER BY updated_at DESC LIMIT 5",
        params,
    ).fetchall()

    return [{"content": r["content"], "category": r["category"]} for r in rows]


def _find_similar(content: str, category: str) -> dict | None:
    """Find an existing memory that's similar enough to update."""
    stop = {"the", "a", "an", "is", "are", "in", "on", "at", "to", "for",
            "of", "and", "or", "my", "i", "that", "this", "it", "with",
            "from", "about", "have", "has", "was", "were", "be", "been"}
    words = [w for w in content.lower().split() if w not in stop and len(w) > 2]

    if not words:
        return None

    rows = _db().execute(
        "SELECT * FROM memories WHERE category = ? ORDER BY updated_at DESC",
        (category,),
    ).fetchall()

    for row in rows:
        row_words = set(row["content"].lower().split())
        matching = sum(1 for w in words if w in row_words)
        if matching >= max(2, len(words) // 2):
            return dict(row)

    return None


def db_path() -> str:
    return str(_DB_PATH)
