from __future__ import annotations

import json

from logs.logger import logger

from brain.memory.memory_decision import MemoryDecision
from brain.memory.memory_types import MemoryType


class MemoryParser:
    """
    Parses LLM output into a MemoryDecision.
    """

    # ---------------------------------------------------------

    def parse(
        self,
        text: str,
    ) -> MemoryDecision | None:

        try:

            text = self._clean(text)

            data = json.loads(text)

            return MemoryDecision(

                should_store=data.get(

                    "should_store",

                    False,

                ),

                memory_type=MemoryType(

                    data.get(

                        "memory_type",

                        "episodic",

                    )

                ),

                importance=float(

                    data.get(

                        "importance",

                        0.0,

                    )

                ),

                summary=data.get(

                    "summary",

                    "",

                ),

                reason=data.get(

                    "reason",

                    "",

                ),

                tags=data.get(

                    "tags",

                    [],

                ),

                relationships=data.get(

                    "relationships",

                    [],

                ),

                confidence=float(

                    data.get(

                        "confidence",

                        1.0,

                    )

                ),

            )

        except Exception as e:

            logger.exception(e)

            return None

    # ---------------------------------------------------------

    def _clean(
        self,
        text: str,
    ) -> str:

        text = text.strip()

        if text.startswith("```"):

            lines = text.splitlines()

            if lines:

                lines = lines[1:]

            if lines and lines[-1].startswith("```"):

                lines = lines[:-1]

            text = "\n".join(lines)

        return text.strip()