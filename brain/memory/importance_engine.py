from __future__ import annotations

from brain.llm.llm_request import LLMRequest
from brain.llm.llm_service import LLMService

from brain.memory.memory_decision import MemoryDecision
from brain.memory.memory_parser import MemoryParser
from brain.memory.memory_prompt import MEMORY_PROMPT


class ImportanceEngine:
    """
    Mike's Memory Decision Engine.

    Determines whether information should be
    remembered using semantic understanding.
    """

    # ---------------------------------------------------------

    def __init__(self):

        self.llm = LLMService()

        self.parser = MemoryParser()

    # ---------------------------------------------------------

    def evaluate(
        self,
        message: str,
    ) -> MemoryDecision:

        request = LLMRequest(

            system_prompt=MEMORY_PROMPT,

            user_input=message,

            parser=self.parser,

            metadata={

                "task": "memory"

            },

        )

        response = self.llm.run(

            request

        )

        if response.success and response.parsed:

            return response.parsed

        return MemoryDecision()