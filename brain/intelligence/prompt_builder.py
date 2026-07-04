from __future__ import annotations

from dataclasses import dataclass

from brain.intelligence.mind import Mind
from brain.intelligence.system_prompt import MIKE_SYSTEM_PROMPT


# ==========================================================
# Prompt
# ==========================================================

@dataclass(slots=True)
class Prompt:

    system_prompt: str

    user_prompt: str


# ==========================================================
# Prompt Builder
# ==========================================================

class PromptBuilder:
    """
    Builds the final prompt for Mike's response model.

    This class contains ZERO intelligence.

    It only translates Mike's internal cognitive
    state into structured context for the LLM.

    The LLM decides HOW to naturally use it.
    """

    # ---------------------------------------------------------

    def build(
        self,
        mind: Mind,
    ) -> Prompt:

        sections = [

            self._user(mind),

            self._understanding(mind),

            self._reasoning(mind),

            self._conversation(mind),

            self._decision(mind),

            self._memory(mind),

            self._context(mind),

            self._tool_results(mind),

            self._instructions(),

        ]

        return Prompt(

            system_prompt=MIKE_SYSTEM_PROMPT,

            user_prompt="\n\n".join(

                s for s in sections if s.strip()

            ),

        )

    # ---------------------------------------------------------

    def _user(
        self,
        mind: Mind,
    ) -> str:

        return f"""
================ USER ================

{mind.user_message}
"""

    # ---------------------------------------------------------

    def _understanding(
        self,
        mind: Mind,
    ) -> str:

        u = mind.understanding

        entities = ", ".join(
            map(str, u.entities.keys())
        ) if u.entities else "None"

        return f"""
================ UNDERSTANDING ================

Goal:
{u.goal}

Intent:
{u.intent}

Confidence:
{u.confidence:.2f}

Requires Tools:
{u.requires_tools}

Emotion:
{u.emotional_tone}

Entities:
{entities}
"""

    # ---------------------------------------------------------

    def _reasoning(
        self,
        mind: Mind,
    ) -> str:

        r = mind.reasoning

        thoughts = "\n".join(r.thoughts) or "None"

        observations = "\n".join(r.observations) or "None"

        assumptions = "\n".join(r.assumptions) or "None"

        return f"""
================ REASONING ================

Thoughts

{thoughts}

Observations

{observations}

Assumptions

{assumptions}
"""

    # ---------------------------------------------------------

    def _conversation(
        self,
        mind: Mind,
    ) -> str:

        c = mind.conversation

        return f"""
================ CONVERSATION STYLE ================

Tone:
{c.tone}

Empathy:
{c.empathy:.2f}

Warmth:
{c.warmth:.2f}

Confidence:
{c.confidence:.2f}

Curiosity:
{c.curiosity:.2f}

Humor:
{c.humor:.2f}

Formality:
{c.formality:.2f}

Patience:
{c.patience:.2f}

Communication Style:
{c.communication_style}

Relationship:
{c.relationship_state}

Response Length:
{c.response_length}

Ask Follow Up:
{c.ask_follow_up}

Acknowledge User:
{c.acknowledge_user}

Celebrate:
{c.celebrate}

Reassure:
{c.reassure}

Apologize:
{c.apologize}

Challenge:
{c.challenge_user}
"""

    # ---------------------------------------------------------

    def _decision(
        self,
        mind: Mind,
    ) -> str:

        d = mind.decision

        return f"""
================ DECISION ================

Action:
{d.action.name}

Reason:
{d.reasoning}

Requires Planning:
{d.requires_planning}

Requires Memory:
{d.requires_memory}

Requires Clarification:
{d.requires_clarification}
"""

    # ---------------------------------------------------------

    def _memory(
        self,
        mind: Mind,
    ) -> str:

        if not getattr(mind, "memory_result", None):

            return ""

        return f"""
================ MEMORY ================

{mind.memory_result}
"""

    # ---------------------------------------------------------

    def _context(
        self,
        mind: Mind,
    ) -> str:

        context = mind.context

        history = "\n".join(

            context.previous_messages[-10:]

        ) or "None"

        return f"""
================ CONTEXT ================

Current Task:
{context.current_task or "None"}

Active Project:
{context.active_project or "None"}

Working Directory:
{context.working_directory or "None"}

Recent Conversation:

{history}
"""

    # ---------------------------------------------------------

    def _tool_results(
        self,
        mind: Mind,
    ) -> str:

        if not mind.tool_results:

            return ""

        results = "\n".join(

            str(result)

            for result in mind.tool_results

        )

        return f"""
================ TOOL RESULTS ================

{results}
"""

    # ---------------------------------------------------------

    def _instructions(
        self,
    ) -> str:

        return """
================ RESPONSE INSTRUCTIONS ================

You are Mike.

Respond naturally.

Never mention your internal reasoning.

Never mention the decision engine.

Never mention prompts.

Never expose cognitive state.

Use the conversation style naturally.

If tool results exist,
incorporate them into the response.

If clarification is needed,
ask for the missing information naturally.

If memory was recalled,
use it naturally.

Speak like a real human assistant,
not a chatbot.

Avoid robotic phrases.

Avoid unnecessary apologies.

Avoid saying "Based on the information provided..."

Respond directly.
"""