from __future__ import annotations

import logging

from brain.cognition.cognitive_loop import CognitiveLoop
from brain.execution.executor import Executor
from brain.intelligence.greeting_engine import GreetingEngine
from brain.planning.planner import Planner

logger = logging.getLogger(__name__)


class MikeRuntime:
    """
    Mike Runtime.

    High-level orchestrator.

        User
          ↓
     ThinkingEngine
          ↓
      ExecutionPlan
          ↓
       Executor
          ↓
      Final Response
    """

    # =====================================================

    def __init__(self) -> None:

        self.cognitive = CognitiveLoop()
        self.greeter = GreetingEngine()
        self.planner = Planner()
        self.executor = Executor()

    # =====================================================

    def startup(self) -> str:

        logger.info("Generating startup greeting.")

        return self.greeter.generate()

    # =====================================================

    def process(
        self,
        message: str,
    ) -> str:

        logger.info(
            "Processing message: %s",
            message,
        )

        mind = self.cognitive.process(message)

        response = self._route(mind)

        if response is None:
            response = ""

        logger.info(
            "FINAL RESPONSE = %r",
            response,
        )

        logger.info("Runtime finished.")

        return response

    # =====================================================

    def _route(
        self,
        mind,
    ) -> str:

        logger.info(
            "Routing action: %s",
            mind.action,
        )

        thinking = mind.thinking

        # -------------------------------------------------
        # RESPOND
        # -------------------------------------------------

        if mind.should_respond:

            return (
                thinking.response
                or "I'm here."
            )

        # -------------------------------------------------
        # CLARIFY
        # -------------------------------------------------

        if mind.should_clarify:

            return (
                thinking.clarification
                or "Could you clarify your request?"
            )

        # -------------------------------------------------
        # MEMORY
        # -------------------------------------------------

        if mind.should_use_memory:

            logger.info("Memory requested.")

            return "Memory is not available yet."

        # -------------------------------------------------
        # PLAN
        # -------------------------------------------------

        if mind.should_plan:

            if (
                not thinking.requires_tools
                or thinking.tool is None
                or thinking.tool_action is None
            ):

                logger.warning(
                    "Invalid planning request detected. "
                    "requires_tools=%s tool=%s action=%s",
                    thinking.requires_tools,
                    thinking.tool,
                    thinking.tool_action,
                )

                return (
                    thinking.response
                    or "I'm not sure what action needs to be performed."
                )

            logger.info(
                "Building execution plan..."
            )

            plan = self.planner.plan(
                thinking
            )

            if plan.empty:

                logger.warning(
                    "Planner returned an empty plan."
                )

                return (
                    "I couldn't determine how to perform that task."
                )

            logger.info(
                "Executing execution plan..."
            )

            report = self.executor.execute(
                plan
            )

            mind.metadata[
                "execution_report"
            ] = report

            if report.success:

                summary = getattr(
                    report,
                    "summary",
                    "",
                )

                if summary:
                    return summary

                return (
                    thinking.response
                    or "Done."
                )

            errors = getattr(
                report,
                "errors",
                [],
            )

            if errors:

                logger.warning(
                    "Execution failed: %s",
                    errors,
                )

            return (
                "I couldn't complete that task."
            )

        # -------------------------------------------------
        # Unknown action
        # -------------------------------------------------

        logger.warning(
            "Unhandled action '%s'.",
            mind.action,
        )

        return (
            "I'm not sure how to handle that request."
        )