from __future__ import annotations

import json
import logging
import re

from brain.cognition.models.cognition_state import CognitionState
from brain.llm.llm_request import LLMRequest
from brain.llm.llm_service import LLMService
from brain.planning.execution_plan import ExecutionPlan
from brain.planning.llm.planning_prompt import PLANNING_SYSTEM_PROMPT
from brain.planning.task import Task

logger = logging.getLogger(__name__)


class LLMPlanner:
    """
    Expands a high-level goal into executable tasks.

    The planner may create multiple tasks, but it must ONLY use
    tools that exist in the system.
    """

    def __init__(self) -> None:

        self._llm = LLMService()

    # =====================================================

    def plan(
        self,
        state: CognitionState,
        available_tools: str,
    ) -> ExecutionPlan:

        logger.info("LLM Planner started.")

        request = LLMRequest(

            system_prompt=PLANNING_SYSTEM_PROMPT,

            user_input=f"""
Goal
====

{state.goal}

Intent
======

{state.intent}

Decision Engine Output
======================

Suggested Tool:
{state.tool}

Suggested Action:
{state.tool_action}

Suggested Arguments:

{json.dumps(state.arguments, indent=2)}

Available Tools
===============

{available_tools}

Rules

- Prefer the Decision Engine suggestion.
- Only use tools from Available Tools.
- Never invent a new tool.
- Never invent a new action.
- Return ONLY JSON.
""".strip(),

            metadata={
                "task": "planning",
            },

        )

        response = self._llm.run(request)

        logger.info("========== PLANNER RAW RESPONSE ==========")
        logger.info(response.text)
        logger.info("==========================================")

        plan = ExecutionPlan(
            goal=state.goal or state.intent
        )

        try:

            payload = json.loads(
                self._extract_json(response.text)
            )

        except Exception:

            logger.exception("Planner failed to parse JSON.")

            return self._fallback_plan(state, plan)

        tasks = payload.get("tasks", [])

        if not isinstance(tasks, list):

            logger.warning("Planner returned invalid task list.")

            return self._fallback_plan(state, plan)

        for item in tasks:

            if not isinstance(item, dict):
                continue

            tool = item.get("tool")
            action = item.get("action")

            if not tool or not action:

                logger.warning("Skipping invalid planner task.")

                continue

            plan.add_task(

                Task(

                    tool=tool,

                    action=action,

                    description=item.get(
                        "description",
                        action,
                    ),

                    arguments=item.get(
                        "arguments",
                        {},
                    ),

                )

            )

        #
        # Never return an empty plan if Decision already
        # decided execution is required.
        #

        if not plan.tasks:

            logger.warning(
                "Planner returned no tasks. Falling back to Decision."
            )

            return self._fallback_plan(state, plan)

        logger.info(
            "Planner generated %d task(s).",
            len(plan.tasks),
        )

        return plan

    # =====================================================

    def _fallback_plan(
        self,
        state: CognitionState,
        plan: ExecutionPlan,
    ) -> ExecutionPlan:

        if state.tool and state.tool_action:

            logger.info(
                "Creating fallback task from Decision Engine."
            )

            plan.add_task(

                Task(

                    tool=state.tool,

                    action=state.tool_action,

                    description=state.goal or state.tool_action,

                    arguments=dict(state.arguments),

                )

            )

        return plan

    # =====================================================

    @staticmethod
    def _extract_json(
        text: str,
    ) -> str:

        text = text.strip()

        if text.startswith("```"):

            text = re.sub(
                r"^```(?:json)?",
                "",
                text,
                flags=re.IGNORECASE,
            )

            text = re.sub(
                r"```$",
                "",
                text,
            ).strip()

        start = text.find("{")
        end = text.rfind("}")

        if start == -1 or end == -1:

            raise ValueError("Planner returned no JSON.")

        return text[start:end + 1]