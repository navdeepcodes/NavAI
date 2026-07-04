from __future__ import annotations

from brain.memory.importance_engine import ImportanceEngine
from brain.memory.memory_models import Memory
from brain.memory.memory_store import MemoryStore


class MemoryManager:
    """
    Responsible for creating, updating and deleting memories.
    """

    # ---------------------------------------------------------

    def __init__(
        self,
        store: MemoryStore,
    ):

        self.store = store

        self.importance = ImportanceEngine()

    # ---------------------------------------------------------

    def remember(
        self,
        memory: Memory,
    ) -> Memory:

        memory.importance = self.importance.score(
            memory
        )

        self.store.save(
            memory
        )

        return memory

    # ---------------------------------------------------------

    def forget(
        self,
        memory_id: str,
    ) -> None:

        self.store.delete(
            memory_id
        )

    # ---------------------------------------------------------

    def update(
        self,
        memory: Memory,
    ) -> Memory:

        memory.update()

        memory.importance = self.importance.score(
            memory
        )

        self.store.save(
            memory
        )

        return memory