from brain.prompts import SYSTEM_PROMPT

from brain.models import (
    Conversation,
    Message,
    Role
)


class PromptBuilder:

    def __init__(

        self,

        conversation: Conversation

    ):

        self.conversation = conversation

    # -----------------------------------------

    def build(self):

        lines = [

            SYSTEM_PROMPT,

            ""

        ]

        for message in self.conversation.messages:

            lines.append(

                self._format(

                    message

                )

            )

        return "\n".join(

            lines

        )

    # -----------------------------------------

    def _format(

        self,

        message: Message

    ):

        role = {

            Role.SYSTEM: "SYSTEM",

            Role.USER: "USER",

            Role.ASSISTANT: "ASSISTANT",

            Role.TOOL: "TOOL"

        }[

            message.role

        ]

        return (

            f"{role}: "

            f"{message.content}"

        )