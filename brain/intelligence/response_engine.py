from __future__ import annotations

import logging

from brain.intelligence.mind import Mind
from brain.intelligence.models import Response
from brain.intelligence.prompt_builder import PromptBuilder

from brain.llm.llm_request import LLMRequest
from brain.llm.llm_service import LLMService


logger = logging.getLogger(__name__)


class ResponseEngine:
    """
    Mike's Natural Language Generation Engine.

    Responsibilities
    ----------------
    • Generate the final response.
    • Respect Mike's conversation style.
    • Never reason.
    • Never plan.
    • Never execute tools.
    • Never modify memory.

    Input:

        Mind

    Output:

        Response
    """

    # ---------------------------------------------------------

    def __init__(self):

        self.llm = LLMService()

        self.builder = PromptBuilder()

    # ---------------------------------------------------------

    def generate(
        self,
        mind: Mind,
    ) -> Response:

        logger.info("Generating natural response...")

        try:

            prompt = self.builder.build(
                mind
            )

            request = LLMRequest(

                system_prompt=prompt.system_prompt,

                user_input=prompt.user_prompt,

                metadata={

                    "task": "response",

                    "decision": mind.decision.action.name,

                    "intent": mind.understanding.intent,

                    "goal": mind.understanding.goal,

                    "tone": mind.conversation.tone,

                },

            )

            result = self.llm.run(request)

            if result is None:

                raise RuntimeError(
                    "Response LLM returned None."
                )

            text = result.text.strip()

            if not text:

                raise RuntimeError(
                    "Response LLM returned empty text."
                )

            logger.info("Response generated successfully.")

            return Response(

                text=text,

                confidence=mind.confidence.score,

            )

        except Exception:

            logger.exception(
                "Response generation failed."
            )

            return Response(

                text=(
                    "Something went wrong while generating "
                    "my response. Could you try asking again?"
                ),

                confidence=0.0,

            )