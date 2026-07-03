from __future__ import annotations

from logs.logger import logger

from brain.provider import get_provider
from brain.planner_prompt import PLANNER_PROMPT
from brain.planner_parser import PlannerParser
from brain.planner_validator import PlannerValidator

from brain.task import Task


class Planner:
    """
    Generates executable tasks from a natural language request.

    Pipeline:

        LLM
          ↓
        Parser
          ↓
        Validator
          ↓
        List[Task]
    """

    # ---------------------------------------------------------

    def __init__(self):

        self.provider = get_provider()

        self.parser = PlannerParser()

        self.validator = PlannerValidator()

    # ---------------------------------------------------------

    def plan(
        self,
        request: str
    ) -> list[Task]:

        logger.info(
            "Planning request..."
        )

        prompt = self._build_prompt(
            request
        )

        response = self.provider.complete(
            prompt
        )

        tasks = self.parser.parse(
            response
        )

        tasks = self.validator.validate(
            tasks
        )

        logger.info(

            f"Planning complete: "

            f"{len(tasks)} task(s)."

        )

        return tasks

    # ---------------------------------------------------------

    def _build_prompt(
        self,
        request: str
    ) -> str:

        return f"""

{PLANNER_PROMPT}

User:

{request}

JSON:

"""