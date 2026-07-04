from __future__ import annotations

from brain.intelligence.thinking_result import ThinkingResult

from brain.llm.llm_request import LLMRequest
from brain.llm.llm_service import LLMService

from brain.response.response_plan import ResponsePlan
from brain.response.response_prompt import RESPONSE_SYSTEM_PROMPT


class ResponseGenerator:

    def __init__(self):

        self.llm = LLMService()

    # -------------------------------------------------

    def generate(

        self,

        thinking: ThinkingResult,

        plan: ResponsePlan,

    ) -> str:

        request = LLMRequest(

            system_prompt=RESPONSE_SYSTEM_PROMPT,

            user_input=f"""

Intent:
{thinking.intent}

Goal:
{thinking.goal}

Emotion:
{thinking.emotion}

Tone:
{thinking.tone}

Action:
{thinking.action}

Depth:
{plan.depth.value}

Style:
{plan.style}

Sections:
{plan.sections}

Examples:
{plan.include_examples}

Summary:
{plan.include_summary}

Next Step:
{plan.include_next_step}

User Request:

Generate the best possible response.

""",

            metadata={

                "task": "response",

            },

        )

        response = self.llm.run(
            request
        )

        return response.text.strip()