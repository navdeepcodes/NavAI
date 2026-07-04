from __future__ import annotations

import logging

from brain.cognition.cognitive_loop import CognitiveLoop
from brain.executor import Executor
from brain.intelligence.enums import DecisionAction
from brain.intelligence.greeting_engine import GreetingEngine
from brain.intelligence.response_engine import ResponseEngine
from brain.planner import Planner

logger = logging.getLogger(__name__)


class MikeRuntime:
    """
    Mike Runtime

    The single entry point into Mike.

    Responsibilities
    ----------------
    • Run the cognitive pipeline.
    • Route cognitive decisions.
    • Coordinate planners and tools.
    • Never perform reasoning.
    • Never contain business logic.
    • Never decide what Mike should do.

    The Runtime simply orchestrates Mike's subsystems.
    """

    # ---------------------------------------------------------

    def __init__(self):

        self.cognitive = CognitiveLoop()

        self.greeter = GreetingEngine()

        self.planner = Planner()

        self.executor = Executor()

        self.responder = ResponseEngine()

    # ---------------------------------------------------------
    # Startup
    # ---------------------------------------------------------

    def startup(self) -> str:

        logger.info("Generating startup greeting.")

        return self.greeter.generate()

    # ---------------------------------------------------------
    # Conversation
    # ---------------------------------------------------------

    def process(
        self,
        message: str,
    ) -> str:

        logger.info("Processing message: %s", message)

        mind = self.cognitive.process(message)

        self._route(mind)

        response = self.responder.generate(mind)

        logger.info("Runtime finished.")

        return response.text

    # ---------------------------------------------------------
    # Decision Router
    # ---------------------------------------------------------

    def _route(
        self,
        mind,
    ) -> None:

        action = mind.decision.action

        logger.info("Routing action: %s", action.name)

        # -------------------------------------------------

        if action == DecisionAction.RESPOND:

            logger.info(
                "Responding directly using reasoning."
            )

            return

        # -------------------------------------------------

        if action == DecisionAction.MEMORY:

            logger.info(
                "Memory requested."
            )

            # Memory engine will be plugged in later.
            return

        # -------------------------------------------------

        if action == DecisionAction.CLARIFY:

            logger.info(
                "Clarification requested."
            )

            if not mind.decision.clarification_question:

                mind.decision.clarification_question = (
                    "Could you provide a little more detail?"
                )

            return

        # -------------------------------------------------

        if action == DecisionAction.PLAN:

            logger.info(
                "Planning requested."
            )

            tasks = self.planner.plan(
                mind.user_message
            )

            mind.planner_tasks.extend(tasks)

            for task in tasks:

                try:

                    result = self.executor.execute(task)

                    if result is not None:

                        mind.tool_results.append(result)

                except Exception:

                    logger.exception(
                        "Task execution failed."
                    )

            return

        # -------------------------------------------------

        logger.warning(
            "Unknown decision '%s'.",
            action,
        )