from __future__ import annotations

from brain.cognition.models.cognition_state import CognitionState
from brain.llm.llm_request import LLMRequest
from brain.llm.llm_service import LLMService
from brain.response.response_plan import ResponsePlan
from brain.response.response_prompt import RESPONSE_SYSTEM_PROMPT


class ResponseGenerator:
    """
    Generates Mike's final natural-language reply.

    This class NEVER performs reasoning.

    Understanding, decision making, planning and execution
    have already completed.

    The model's only job is to communicate naturally.
    """

    def __init__(self) -> None:
        self._llm = LLMService()

    # =====================================================

    def generate(
        self,
        *,
        state: CognitionState,
        plan: ResponsePlan,
    ) -> str:

        goal = ""

        if state.goal is not None:
            goal = getattr(
                state.goal,
                "description",
                str(state.goal),
            )

        execution_report = ""

        if state.metadata:
            report = state.metadata.get(
                "execution_report"
            )

            if report:
                execution_report = str(report)

        context = (
            state.raw_context.strip()
            if state.raw_context.strip()
            else "No previous conversation."
        )

        tool = state.tool or "None"

        tool_action = state.tool_action or "None"

        arguments = state.arguments or {}

        prompt = f"""
==========================
CONVERSATION
==========================

{context}

==========================
LATEST USER MESSAGE
==========================

{state.user_message}

==========================
UNDERSTANDING
==========================

Intent:
{state.intent}

Goal:
{goal}

Emotion:
{state.emotion}

Confidence:
{state.confidence:.2f}

==========================
DECISION
==========================

Chosen Action:
{state.action}

Requires Tool:
{state.requires_tools}

Tool:
{tool}

Tool Action:
{tool_action}

Arguments:
{arguments}

==========================
EXECUTION
==========================

{execution_report if execution_report else "No tool was executed."}

==========================
RESPONSE STYLE
==========================

Depth:
{plan.depth.value}

Reply naturally.

Use the understanding and decision above.

Do not classify.

Do not explain internal reasoning.

Do not mention intents.

Do not mention actions.

Do not mention tools unless they were actually used.

If no tool was executed, simply converse naturally.

Only answer the user's latest message.

Never repeat previous replies.

Never output JSON.
""".strip()

        request = LLMRequest(
            system_prompt=RESPONSE_SYSTEM_PROMPT,
            user_input=prompt,
            metadata={
                "task": "conversation",
            },
            temperature=0.7,
            max_tokens=300,
        )

        response = self._llm.run(request)

        return response.text.strip()