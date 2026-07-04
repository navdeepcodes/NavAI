from __future__ import annotations

from brain.intelligence.mind import Mind

from brain.response.response_formatter import ResponseFormatter
from brain.response.response_generator import ResponseGenerator
from brain.response.response_planner import ResponsePlanner


class ResponseEngine:
    """
    Converts Mike's internal thinking into the final
    user-visible response.
    """

    def __init__(self) -> None:

        self.planner = ResponsePlanner()

        self.generator = ResponseGenerator()

        self.formatter = ResponseFormatter()

    # -----------------------------------------------------

    def generate(
        self,
        mind: Mind,
    ) -> str:

        plan = self.planner.plan(
            mind.thinking,
        )

        text = self.generator.generate(

            thinking=mind.thinking,

            plan=plan,

        )

        text = self.formatter.format(
            text
        )

        mind.final_response = text

        return text