from __future__ import annotations

from brain.cognition.models.cognition_state import CognitionState
from brain.planning.execution_plan import ExecutionPlan
from brain.planning.task import Task


class GoalPlanner:
    """
    Converts high-level execution goals into executable tasks.

    The LLM decides WHAT.

    The GoalPlanner decides HOW.
    """

    def build(
        self,
        state: CognitionState,
    ) -> ExecutionPlan:

        plan = ExecutionPlan(
            goal=state.goal or state.action
        )

        goal = (state.goal or "").lower()

        # -------------------------------------------------
        # YouTube Search
        # -------------------------------------------------

        if "youtube" in goal and "search" in goal:

            query = (
                state.arguments.get("query")
                or state.arguments.get("search")
                or ""
            )

            plan.add_task(
                Task(
                    tool="browser",
                    action="open_url",
                    description="Open YouTube",
                    arguments={
                        "url": "https://youtube.com"
                    },
                )
            )

            plan.add_task(
                Task(
                    tool="browser",
                    action="search",
                    description="Search YouTube",
                    arguments={
                        "query": query
                    },
                )
            )

            return plan

        return plan