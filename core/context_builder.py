from memory.working_memory import WorkingMemory

from brain.models import (
    Conversation,
    Message,
    Role,
)


class ContextBuilder:

    def __init__(self):

        self.working = WorkingMemory()

    # ---------------------------------------------------------

    def build(

        self,

        system_prompt: str,

        long_term: str,

        history,

    ) -> Conversation:

        conversation = Conversation()

        # -------------------------------------------------
        # System Prompt
        # -------------------------------------------------

        conversation.add(

            Message(

                role=Role.SYSTEM,

                content=system_prompt,

            )

        )

        # -------------------------------------------------
        # Working Memory
        # -------------------------------------------------

        working = self.working.all()

        if working:

            text = "\n".join(

                f"{key}: {value}"

                for key, value in working.items()

            )

            conversation.add(

                Message(

                    role=Role.SYSTEM,

                    content=

                    "Working Memory\n\n"

                    + text,

                )

            )

        # -------------------------------------------------
        # Long-Term Memory
        # -------------------------------------------------

        if long_term:

            conversation.add(

                Message(

                    role=Role.SYSTEM,

                    content=

                    "Long-Term Memory\n\n"

                    + long_term,

                )

            )

        # -------------------------------------------------
        # Previous Conversation
        # -------------------------------------------------

        for item in history:

            role = Role(

                item["role"]

            )

            conversation.add(

                Message(

                    role=role,

                    content=item["content"],

                )

            )

        return conversation