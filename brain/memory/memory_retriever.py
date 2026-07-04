from __future__ import annotations

from brain.memory.memory_models import Memory
from brain.memory.memory_store import MemoryStore
from brain.memory.memory_types import MemoryType


class MemoryRetriever:
    """
    Retrieves memories from the shared memory store.
    """

    # ---------------------------------------------------------

    def __init__(
        self,
        store: MemoryStore,
    ):

        self.store = store

    # ---------------------------------------------------------

    def recent(
        self,
        limit: int = 10,
    ) -> list[Memory]:

        memories = sorted(

            self.store.all(),

            key=lambda memory: memory.updated_at,

            reverse=True,

        )

        return memories[:limit]

    # ---------------------------------------------------------

    def by_type(
        self,
        memory_type: MemoryType,
    ) -> list[Memory]:

        return [

            memory

            for memory in self.store.all()

            if memory.type == memory_type

        ]

    # ---------------------------------------------------------

    def all(
        self,
    ) -> list[Memory]:

        return self.store.all()

    # ---------------------------------------------------------

    def get(
        self,
        memory_id: str,
    ) -> Memory | None:

        return self.store.get(
            memory_id
        )