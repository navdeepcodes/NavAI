from __future__ import annotations

from brain.memory.importance_engine import ImportanceEngine
from brain.memory.memory_decision import MemoryDecision
from brain.memory.memory_manager import MemoryManager
from brain.memory.memory_models import Memory
from brain.memory.memory_retriever import MemoryRetriever
from brain.memory.memory_store import MemoryStore
from brain.memory.memory_types import MemoryType


class MemoryEngine:
    """
    Mike's long-term memory engine.

    Responsibilities

    - Evaluate conversations
    - Decide what should be remembered
    - Store memories
    - Retrieve memories
    """

    # ---------------------------------------------------------

    def __init__(self):

        self.store = MemoryStore()

        self.manager = MemoryManager(

            self.store

        )

        self.retriever = MemoryRetriever(

            self.store

        )

        self.importance = ImportanceEngine()

    # ---------------------------------------------------------

    def evaluate(
        self,
        message: str,
    ) -> MemoryDecision:

        return self.importance.evaluate(

            message

        )

    # ---------------------------------------------------------

    def remember(
        self,
        memory: Memory,
    ) -> Memory:

        return self.manager.remember(

            memory

        )

    # ---------------------------------------------------------

    def process(
        self,
        message: str,
        memory: Memory,
    ) -> MemoryDecision:

        decision = self.evaluate(

            message

        )

        if decision.should_store:

            memory.type = decision.memory_type

            memory.summary = decision.summary

            memory.importance = decision.importance

            memory.tags = decision.tags

            memory.relationships = (

                decision.relationships

            )

            self.remember(

                memory

            )

        return decision

    # ---------------------------------------------------------

    def forget(
        self,
        memory_id: str,
    ) -> None:

        self.manager.forget(

            memory_id

        )

    # ---------------------------------------------------------

    def update(
        self,
        memory: Memory,
    ) -> Memory:

        return self.manager.update(

            memory

        )

    # ---------------------------------------------------------

    def get(
        self,
        memory_id: str,
    ) -> Memory | None:

        return self.retriever.get(

            memory_id

        )

    # ---------------------------------------------------------

    def recent(
        self,
        limit: int = 10,
    ) -> list[Memory]:

        return self.retriever.recent(

            limit

        )

    # ---------------------------------------------------------

    def by_type(
        self,
        memory_type: MemoryType,
    ) -> list[Memory]:

        return self.retriever.by_type(

            memory_type

        )

    # ---------------------------------------------------------

    def all(
        self,
    ) -> list[Memory]:

        return self.retriever.all()