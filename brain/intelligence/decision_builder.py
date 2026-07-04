from __future__ import annotations

from brain.intelligence.models import (
    Context,
    Reasoning,
    Understanding,
)


class DecisionPromptBuilder:
    """
    Builds the prompt for Mike's Executive Decision LLM.

    Responsibilities
    ----------------
    • Convert Mike's cognitive state into prompt context.
    • Provide only the information required to make a decision.
    • Never perform reasoning itself.
    """

    # ---------------------------------------------------------

    def build(
        self,
        *,
        user_message: str,
        understanding: Understanding,
        reasoning: Reasoning,
        context: Context,
    ) -> str:

        sections = [

            self._user(user_message),

            self._understanding(understanding),

            self._reasoning(reasoning),

            self._context(context),

            self._capabilities(),

            self._task(),

        ]

        return "\n\n".join(
            section.strip()
            for section in sections
            if section.strip()
        )

    # ---------------------------------------------------------

    def _user(
        self,
        message: str,
    ) -> str:

        return f"""
### USER MESSAGE

{message}
"""

    # ---------------------------------------------------------

    def _understanding(
        self,
        understanding: Understanding,
    ) -> str:

        entities = ", ".join(

            f"{k}: {v}"

            for k, v in understanding.entities.items()

        ) if understanding.entities else "None"

        constraints = ", ".join(

            f"{k}: {v}"

            for k, v in understanding.constraints.items()

        ) if understanding.constraints else "None"

        return f"""
### UNDERSTANDING

Goal:
{understanding.goal}

Intent:
{understanding.intent}

Requires Tools:
{understanding.requires_tools}

Confidence:
{understanding.confidence:.2f}

Entities:
{entities}

Constraints:
{constraints}
"""

    # ---------------------------------------------------------

    def _reasoning(
        self,
        reasoning: Reasoning,
    ) -> str:

        thoughts = "\n".join(
            f"- {t}"
            for t in reasoning.thoughts
        ) or "- None"

        observations = "\n".join(
            f"- {o}"
            for o in reasoning.observations
        ) or "- None"

        assumptions = "\n".join(
            f"- {a}"
            for a in reasoning.assumptions
        ) or "- None"

        return f"""
### REASONING

Thoughts

{thoughts}

Observations

{observations}

Assumptions

{assumptions}
"""

    # ---------------------------------------------------------

    def _context(
        self,
        context: Context,
    ) -> str:

        history = "\n".join(
            context.previous_messages[-10:]
        ) or "None"

        return f"""
### CONTEXT

Current Task

{context.current_task or "None"}

Conversation History

{history}
"""

    # ---------------------------------------------------------

    def _capabilities(
        self,
    ) -> str:

        return """
### MIKE CAPABILITIES

Mike can:

- Hold natural conversations.
- Explain concepts.
- Answer from existing knowledge.
- Write and review code.
- Solve mathematical problems.
- Search long-term memory.
- Browse the web.
- Open websites and applications.
- Manipulate files and folders.
- Execute terminal commands.
- Control desktop tools.

External tools are expensive.

Prefer reasoning whenever reasoning alone satisfies the user's request.

Only choose planning when an external action must actually be performed.
"""

    # ---------------------------------------------------------

    def _task(
        self,
    ) -> str:

        return """
### TASK

Determine Mike's next action.

Do NOT answer the user.

Do NOT create a plan.

Do NOT invent tool calls.

Choose exactly ONE action:

- RESPOND
- PLAN
- MEMORY
- CLARIFY

Return only the information required by the Decision JSON schema.
"""