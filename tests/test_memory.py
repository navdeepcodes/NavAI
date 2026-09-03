"""Tests for Memory V1 — SQLite persistent memory."""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_1_explicit_save():
    """Save a memory and verify it's in SQLite."""
    from brain import memory_store
    memory_store.forget(query="everything")

    result = memory_store.remember(
        content="Main projects are in ~/Developer",
        category="location",
    )
    assert result["status"] == "success"
    assert result["action"] == "created"

    recalled = memory_store.recall(query="projects Developer")
    assert recalled["status"] == "success"
    assert len(recalled["memories"]) >= 1
    assert "Developer" in recalled["memories"][0]["content"]
    print("PASS: Test 1 — Explicit save")


def test_2_persistence():
    """Verify memory survives reconnection."""
    from brain import memory_store

    memory_store._conn = None

    recalled = memory_store.recall(query="projects Developer")
    assert len(recalled["memories"]) >= 1
    assert "Developer" in recalled["memories"][0]["content"]
    print("PASS: Test 2 — Restart persistence (reconnect)")


def test_3_categories():
    """Save memories with different categories."""
    from brain import memory_store

    memory_store.remember("I prefer dark mode", "preference")
    memory_store.remember("Mike AI is my current project", "project")
    memory_store.remember("I use Ollama for local models", "workflow")

    prefs = memory_store.recall(query="", category="preference")
    assert any("dark mode" in m["content"] for m in prefs["memories"])

    projects = memory_store.recall(query="", category="project")
    assert any("Mike AI" in m["content"] for m in projects["memories"])
    print("PASS: Test 3 — Categories")


def test_4_update():
    """Update replaces existing similar memory."""
    from brain import memory_store

    memory_store.remember("Main projects are in ~/Code", "location")

    recalled = memory_store.recall(query="projects")
    contents = [m["content"] for m in recalled["memories"]]
    assert any("~/Code" in c for c in contents)
    developer_count = sum(1 for c in contents if "~/Developer" in c and "~/Code" not in c)
    assert developer_count == 0, f"Old memory not updated: {contents}"
    print("PASS: Test 4 — Update (no duplicates)")


def test_5_forget():
    """Forget a specific memory."""
    from brain import memory_store

    result = memory_store.forget(query="dark mode")
    assert result["status"] == "success"

    recalled = memory_store.recall(query="dark mode")
    assert len(recalled["memories"]) == 0
    print("PASS: Test 5 — Forget specific memory")


def test_6_selective_retrieval():
    """Retrieve only relevant memories."""
    from brain import memory_store

    memory_store.remember("Rocket simulation is in ~/Developer/RocketSim", "project")

    recalled = memory_store.recall(query="rocket")
    assert len(recalled["memories"]) >= 1
    assert all("rocket" in m["content"].lower() or "Rocket" in m["content"]
               for m in recalled["memories"])
    print("PASS: Test 6 — Selective retrieval")


def test_7_auto_recall():
    """Auto-recall finds relevant memories from natural language."""
    from brain import memory_store

    results = memory_store.auto_recall("where is the rocket project?")
    assert len(results) >= 1
    assert any("Rocket" in m["content"] for m in results)
    print("PASS: Test 7 — Auto-recall")


def test_8_no_empty_save():
    """Empty content should fail."""
    from brain import memory_store

    result = memory_store.remember("", "fact")
    assert result["status"] == "error"
    print("PASS: Test 8 — No empty save")


def test_9_clear_all():
    """Clear all memories."""
    from brain import memory_store

    result = memory_store.forget(query="everything")
    assert result["status"] == "success"

    recalled = memory_store.recall()
    assert len(recalled["memories"]) == 0
    print("PASS: Test 9 — Clear all memories")


def test_10_performance():
    """Memory lookup should be under 100ms."""
    from brain import memory_store

    for i in range(50):
        memory_store.remember(f"Test fact number {i} about topic {i % 5}", "fact")

    start = time.monotonic()
    for _ in range(100):
        memory_store.recall(query="topic 3")
    elapsed = (time.monotonic() - start) / 100

    memory_store.forget(query="everything")

    assert elapsed < 0.1, f"Lookup took {elapsed*1000:.1f}ms (target <100ms)"
    print(f"PASS: Test 10 — Performance ({elapsed*1000:.2f}ms per lookup)")


def test_11_db_location():
    """Database is in Application Support, not the source repo."""
    from brain.memory_store import db_path
    path = db_path()
    assert "Application Support" in path or "Library" in path
    assert "NavAI-v0" not in path
    print(f"PASS: Test 11 — DB at {path}")


def test_12_tools_registered():
    """Memory tools exist in Ollama tool list."""
    from brain.core_tools import OLLAMA_TOOLS, MEMORY_TOOLS

    tool_names = {t["function"]["name"] for t in OLLAMA_TOOLS}
    assert "remember" in tool_names
    assert "recall_memory" in tool_names
    assert "forget_memory" in tool_names
    assert MEMORY_TOOLS == {"remember", "recall_memory", "forget_memory"}
    print("PASS: Test 12 — Memory tools registered")


if __name__ == "__main__":
    test_1_explicit_save()
    test_2_persistence()
    test_3_categories()
    test_4_update()
    test_5_forget()
    test_6_selective_retrieval()
    test_7_auto_recall()
    test_8_no_empty_save()
    test_9_clear_all()
    test_10_performance()
    test_11_db_location()
    test_12_tools_registered()
    print("\nAll Memory V1 tests passed.")
