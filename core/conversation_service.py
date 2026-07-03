from logs.logger import logger

from brain.provider import get_provider
from brain.prompts import SYSTEM_PROMPT

from memory.memory_manager import MemoryManager

from core.context_builder import ContextBuilder
from core.state_manager import StateManager
from core.context_updater import ContextUpdater


class ConversationService:

    # ---------------------------------------------------------

    def __init__(self):

        logger.info(
            "Initializing Conversation Service..."
        )

        self.memory = MemoryManager()

        self.context = ContextBuilder()

        self.state = StateManager()

        self.updater = ContextUpdater()

    # ---------------------------------------------------------
    # Main Conversation
    # ---------------------------------------------------------

    def send(
        self,
        message: str
    ):

        logger.info(
            f"User: {message}"
        )

        # -------------------------------------------------
        # Save user message
        # -------------------------------------------------

        self.memory.remember(
            "user",
            message
        )

        # -------------------------------------------------
        # Update working memory
        # -------------------------------------------------

        self.context.working.update_many(

            last_user_message=message

        )

        # -------------------------------------------------
        # Update conversation state
        # -------------------------------------------------

        self.updater.update(

            self.state,

            message

        )

        # -------------------------------------------------
        # Conversation history
        # -------------------------------------------------

        history = self.memory.conversation()

        # -------------------------------------------------
        # Long-term memory
        # -------------------------------------------------

        long_term = self.memory.relevant_memory(
            message
        )

        # -------------------------------------------------
        # Build Conversation model
        # -------------------------------------------------

        conversation = self.context.build(

            SYSTEM_PROMPT,

            long_term,

            history

        )

        # -------------------------------------------------
        # Select provider dynamically
        # -------------------------------------------------

        provider = get_provider()

        logger.info(
            f"Using Provider: {provider.name}"
        )

        # -------------------------------------------------
        # Generate response
        # -------------------------------------------------

        response = provider.chat(
            conversation
        )

        # -------------------------------------------------
        # Save assistant response
        # -------------------------------------------------

        self.memory.remember(

            "assistant",

            response.text

        )

        # -------------------------------------------------
        # Update working memory
        # -------------------------------------------------

        self.context.working.update_many(

            last_assistant_message=response.text,

            current_provider=provider.name

        )

        logger.info(

            f"{provider.name}: {response.text}"

        )

        return response