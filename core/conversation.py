from logs.logger import logger

from brain.provider import get_provider
from brain.prompts import SYSTEM_PROMPT

from memory.memory_manager import MemoryManager

from core.context_builder import ContextBuilder
from core.state_manager import StateManager
from core.context_updater import ContextUpdater


class Conversation:

    def __init__(self):

        logger.info(
            "Initializing Conversation..."
        )

        self.provider = get_provider()

        self.memory = MemoryManager()

        self.context = ContextBuilder()

        self.state = StateManager()

        self.updater = ContextUpdater()

    # -----------------------------------------
    # Main Conversation
    # -----------------------------------------

    def send(
        self,
        message: str
    ):

        logger.info(
            f"User: {message}"
        )

        # -----------------------------------------
        # Save user message
        # -----------------------------------------

        self.memory.remember(
            "user",
            message
        )

        # -----------------------------------------
        # Update working memory
        # -----------------------------------------

        self.context.working.update_many(

            last_user_message=message

        )

        # -----------------------------------------
        # Update conversation state
        # -----------------------------------------

        self.updater.update(

            self.state,

            message

        )

        # -----------------------------------------
        # Collect conversation history
        # -----------------------------------------

        history = self.memory.conversation()

        # -----------------------------------------
        # Retrieve relevant long-term memory
        # -----------------------------------------

        long_term = self.memory.relevant_memory(
            message
        )

        # -----------------------------------------
        # Build AI context
        # -----------------------------------------

        messages = self.context.build(

            SYSTEM_PROMPT,

            long_term,

            history

        )

        # -----------------------------------------
        # Ask provider
        # -----------------------------------------

        response = self.provider.chat(
            messages
        )

        # -----------------------------------------
        # Save assistant response
        # -----------------------------------------

        self.memory.remember(

            "assistant",

            response.text

        )

        self.context.working.update_many(

            last_assistant_message=response.text,

            current_provider=self.provider.name

        )

        logger.info(

            f"{self.provider.name}: {response.text}"

        )

        return response