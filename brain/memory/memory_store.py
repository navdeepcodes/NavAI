from __future__ import annotations

from brain.memory.memory_models import Memory


class MemoryStore:
    """
    Persistent memory storage.

    SQLite implementation will be added later.
    """

    def __init__(self):

        self._memories: dict[str, Memory] = {}

    # ---------------------------------------------------------

    def save(
        self,
        memory: Memory,
    ):

        self._memories[memory.id] = memory

    # ---------------------------------------------------------

    def get(
        self,
        memory_id: str,
    ) -> Memory | None:

        return self._memories.get(memory_id)

    # ---------------------------------------------------------

    def all(
        self,
    ) -> list[Memory]:

        return list(

            self._memories.values()

        )

    # ---------------------------------------------------------

    def delete(
        self,
        memory_id: str,
    ):

        self._memories.pop(

            memory_id,

            None,

        )