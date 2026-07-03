from logs.logger import logger

from brain.intent import IntentEngine
from brain.agent import Agent

from core.conversation_service import ConversationService

from brain.models import ProviderResponse


class Runtime:

    # ---------------------------------------------------------

    def __init__(self):

        logger.info(
            "Initializing Runtime..."
        )

        self.intent = IntentEngine()

        self.conversation = ConversationService()

        self.agent = Agent()

    # ---------------------------------------------------------

    def process(
        self,
        message: str
    ) -> ProviderResponse:

        intent = self.intent.detect(
            message
        )

        logger.info(
            f"Detected Intent: {intent}"
        )

        handlers = {

            "CHAT": self._chat,

            "TOOL": self._tool,

            "PLAN": self._plan,

            "MEMORY": self._memory,

            "VISION": self._vision,

        }

        handler = handlers.get(

            intent,

            self._chat

        )

        return handler(
            message
        )

    # ---------------------------------------------------------
    # Chat
    # ---------------------------------------------------------

    def _chat(
        self,
        message: str
    ) -> ProviderResponse:

        return self.conversation.send(
            message
        )

    # ---------------------------------------------------------
    # Memory
    # ---------------------------------------------------------

    def _memory(
        self,
        message: str
    ) -> ProviderResponse:

        return self.conversation.send(
            message
        )

    # ---------------------------------------------------------
    # Vision
    # ---------------------------------------------------------

    def _vision(
        self,
        message: str
    ) -> ProviderResponse:

        return self.conversation.send(
            message
        )

    # ---------------------------------------------------------
    # Planning
    # ---------------------------------------------------------

    def _plan(
        self,
        message: str
    ) -> ProviderResponse:

        tasks = self.agent.planner.plan(
            message
        )

        text = "\n".join(

            f"• {task.description}"

            for task in tasks

        )

        return ProviderResponse(

            text=text,

            provider="Planner",

            model="planner",

            raw=tasks

        )

    # ---------------------------------------------------------
    # Tool Execution
    # ---------------------------------------------------------

    def _tool(
        self,
        message: str
    ) -> ProviderResponse:

        results = self.agent.run(
            message
        )

        lines = []

        for item in results:

            status = (

                "SUCCESS"

                if item["success"]

                else "FAILED"

            )

            lines.append(

                f"[{status}] {item['task']}"

            )

            if item["result"]:

                lines.append(

                    str(item["result"])

                )

            lines.append("")

        return ProviderResponse(

            text="\n".join(lines).strip(),

            provider="Agent",

            model="executor",

            raw=results

        )