from __future__ import annotations

import logging

from brain.cognition.cognitive_loop import CognitiveLoop
from brain.execution.executor import Executor
from brain.intelligence.greeting_engine import GreetingEngine
from brain.planning.planner import Planner
from brain.response.response_engine import ResponseEngine
from brain.skills.skill_manager import SkillManager

logger = logging.getLogger(__name__)


class MikeRuntime:
    """
    Mike Runtime

        User
          │
          ▼
     CognitiveLoop
          │
          ▼
      SkillManager
          │
          ▼
        Planner
          │
          ▼
        Executor
          │
          ▼
    ResponseEngine
          │
          ▼
         User

    Responsibilities
    ----------------
    • Run one complete cognition cycle.
    • Execute high-confidence skills.
    • Execute plans when required.
    • Generate conversational responses.
    • Persist conversation history.

    Skills classify requests.
    The ResponseEngine generates natural language.
    """

    # =====================================================

    def __init__(self) -> None:

        self.cognitive = CognitiveLoop()

        self.skills = SkillManager()

        self.greeter = GreetingEngine()

        self.planner = Planner()

        self.executor = Executor()

        self.response = ResponseEngine()

    # =====================================================

    def startup(self) -> str:

        logger.info(
            "Generating startup greeting."
        )

        greeting = self.greeter.generate()

        self._remember_reply(
            greeting,
        )

        return greeting

    # =====================================================

    def process(
        self,
        message: str,
    ) -> str:

        logger.info(
            "Processing message: %s",
            message,
        )

        state = self.cognitive.process(
            message,
        )

        # =============================================
        # Skill Layer
        # =============================================

        skill = self.skills.process(
            state,
        )

        if skill.handled:

            logger.info(
                "Handled by skill: %s",
                skill.skill_name,
            )

            # Store skill information so the
            # ResponseEngine can use it later.
            state.metadata.setdefault(
                "skill",
                {},
            )

            state.metadata["skill"].update(
                skill.metadata or {},
            )

            state.metadata["skill_name"] = (
                skill.skill_name
            )

            state.metadata["skill_confidence"] = (
                skill.confidence
            )

            # -----------------------------------------
            # Backwards compatibility.
            #
            # Existing skills already generate replies.
            # Future skills can simply classify and let
            # the ResponseEngine speak naturally.
            # -----------------------------------------

            if skill.response:

                self._remember_reply(
                    skill.response,
                )

                logger.info(
                    "FINAL RESPONSE = %r",
                    skill.response,
                )

                return skill.response

        # =============================================
        # Runtime Pipeline
        # =============================================

        reply = self._route(
            state,
        )

        if not reply:

            logger.error(
                "Runtime produced an empty response."
            )

            reply = (
                "I'm sorry, something went wrong."
            )

        self._remember_reply(
            reply,
        )

        logger.info(
            "FINAL RESPONSE = %r",
            reply,
        )

        logger.info(
            "Runtime finished."
        )

        return reply

    # =====================================================

    def _route(
        self,
        state,
    ) -> str:

        logger.info(
            "Routing action: %s",
            state.action,
        )

        # ---------------------------------------------
        # Conversation
        # ---------------------------------------------

        if state.action == "RESPOND":

            logger.info(
                "Generating conversational response..."
            )

            return self.response.generate(
                state,
            )

        # ---------------------------------------------
        # Clarification
        # ---------------------------------------------

        if state.action == "CLARIFY":

            logger.info(
                "Generating clarification..."
            )

            return (
                state.final_response
                or "Could you clarify your request?"
            )

        # ---------------------------------------------
        # Memory
        # ---------------------------------------------

        if state.action == "MEMORY":

            logger.info(
                "Memory requested."
            )

            return self.response.generate(
                state,
            )

        # ---------------------------------------------
        # Tool execution
        # ---------------------------------------------

        if state.action == "PLAN":

            if not state.requires_tools:

                logger.warning(
                    "PLAN requested but requires_tools=False."
                )

                return (
                    "I couldn't determine what action to perform."
                )

            logger.info(
                "Building execution plan..."
            )

            plan = self.planner.plan(
                state,
            )

            if plan.empty:

                logger.warning(
                    "Planner returned an empty execution plan."
                )

                return (
                    "I couldn't generate an execution plan."
                )

            logger.info(
                "Executing plan..."
            )

            report = self.executor.execute(
                plan,
            )

            state.metadata[
                "execution_report"
            ] = report

            if report.success:

                logger.info(
                    "Execution successful."
                )

            else:

                logger.warning(
                    "Execution failed."
                )

            return self.response.generate(
                state,
            )

        # ---------------------------------------------
        # Unknown
        # ---------------------------------------------

        logger.warning(
            "Unknown action: %s",
            state.action,
        )

        return (
            "I'm not sure how to handle that request."
        )

    # =====================================================

    def _remember_reply(
        self,
        reply: str,
    ) -> None:

        if not reply:
            return

        self.cognitive.add_assistant_message(
            reply,
        )