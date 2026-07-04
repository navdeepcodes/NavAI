from __future__ import annotations

from enum import Enum


class MemoryType(str, Enum):
    """
    Different categories of memories maintained by Mike.
    """

    WORKING = "working"

    EPISODIC = "episodic"

    SEMANTIC = "semantic"

    USER = "user"

    PROJECT = "project"

    PREFERENCE = "preference"

    PROCEDURAL = "procedural"

    TASK = "task"

    KNOWLEDGE = "knowledge"