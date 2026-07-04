from __future__ import annotations

from brain.intelligence.models import (
    Context,
    Reasoning,
    Understanding,
)


class ConversationPromptBuilder:
    """
    Builds context for the Conversation LLM.

    Contains ZERO business logic.
    """

    def build(
        self,
        *,
        user_message: str,
        understanding: Understanding,
        reasoning: Reasoning,
        context: Context,
    ) -> str:

        history = "\n".join(
            context.previous_messages[-8:]
        ) or "None"

        return f"""
USER

{user_message}

--------------------------------

UNDERSTANDING

Goal:
{understanding.goal}

Intent:
{understanding.intent}

Confidence:
{understanding.confidence}

Emotion:
{understanding.emotional_tone}

--------------------------------

REASONING

Thoughts

{chr(10).join(reasoning.thoughts)}

Observations

{chr(10).join(reasoning.observations)}

--------------------------------

RECENT CONVERSATION

{history}

--------------------------------

Determine how Mike should communicate.
Return ONLY JSON.
"""