from brain.provider import get_provider

from brain.planner_prompt import PLANNER_PROMPT
from brain.planner_parser import PlannerParser


class Planner:

    def __init__(self):

        self.provider = get_provider()

        self.parser = PlannerParser()

    def plan(
        self,
        request: str
    ):

        prompt = f"""

{PLANNER_PROMPT}

User:

{request}

JSON:

"""

        result = self.provider.complete(
            prompt
        )

        return self.parser.parse(
            result
        )