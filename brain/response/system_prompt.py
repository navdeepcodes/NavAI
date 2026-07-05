from __future__ import annotations

import logging

from brain.cognition.models.cognition_state import CognitionState

from brain.llm.llm_request import LLMRequest
from brain.llm.llm_service import LLMService

from brain.response.response_plan import ResponsePlan
from brain.response.response_prompt import RESPONSE_SYSTEM_PROMPT
from brain.response.system_prompt import MIKE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class ResponseGenerator:
    """
    Generates Mike's final natural-language response.

    Responsibilities
    ----------------
    • Speak as Mike.
    • Never expose the underlying LLM.
    • Explain execution results naturally.
    • Produce the final user-facing response.
    """

    # =====================================================

    def __init__(self) -> None:

        self._llm = LLMService()

    # =====================================================

    def generate(
        self,
        *,
        state: CognitionState,
        plan: ResponsePlan,
    ) -> str:

        logger.info("Generating response using LLM.")

        system_prompt = f"""
{MIKE_SYSTEM_PROMPT}

------------------------------------------------------------

{RESPONSE_SYSTEM_PROMPT}
""".strip()

        request = LLMRequest(

            system_prompt=system_prompt,

            user_input=f"""
Conversation
============

{state.raw_context}

==================================================

Latest User Message

{state.user_message}

==================================================

Understanding

Intent:
{state.intent}

Goal:
{state.goal}

Emotion:
{state.emotion}

Confidence:
{state.confidence:.2f}

==================================================

Decision

Action:
{state.action}

Tool:
{state.tool}

Tool Action:
{state.tool_action}

Arguments:
{state.arguments}

==================================================

Execution Report

{state.metadata.get("execution_report")}

==================================================

Desired Response Depth

{plan.depth.value}

==================================================

Instructions

Generate Mike's final response.

Speak naturally.

If execution succeeded, describe what happened.

If execution failed, explain the failure politely.

Stay in character as Mike.

Never mention:
- OpenAI
- ChatGPT
- Gemini
- Google AI
- Groq
- Llama
- Qwen
- Alibaba Cloud
- Anthropic
- Claude
- DeepSeek

Never reveal implementation details.

Never output JSON.
""".strip(),

            metadata={
                "task": "response",
            },

        )

        response = self._llm.run(request)

        text = response.text.strip()

        logger.info("Response generated.")

        return text