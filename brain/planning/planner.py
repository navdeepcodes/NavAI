from __future__ import annotations

from logs.logger import logger

from brain.cognition.models.cognition_state import CognitionState
from brain.execution.executor import Executor
from brain.planning.execution_plan import ExecutionPlan
from brain.planning.llm_planner import LLMPlanner


class Planner:
    """
    Mike's planner.

    Responsibilities
    ----------------
    • Convert a CognitionState into an ExecutionPlan.
    • Delegate planning to the LLM planner.
    • Never execute tools.
    """

    def __init__(self) -> None:

        self._planner = LLMPlanner()

    # =====================================================

    def plan(
        self,
        state: CognitionState,
    ) -> ExecutionPlan:

        logger.info("Planning execution...")

        if not state.requires_tools:

            logger.info("No execution required.")

            return ExecutionPlan(
                goal=state.goal or state.intent
            )

        # -------------------------------------------------

        available_tools = self._build_tool_catalog()

        # -------------------------------------------------

        return self._planner.plan(
            state=state,
            available_tools=available_tools,
        )

    # =====================================================

    @staticmethod
    def _build_tool_catalog() -> str:
        """
        Temporary tool catalog.

        Later this will be generated automatically
        from the Tool Registry.
        """

        return """
Browser
--------
open_browser
open_url
search

Filesystem
----------
create_folder
create_file
delete_file
move_file

Terminal
--------
run_command

Email
-----
send_email
"""