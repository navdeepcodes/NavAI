from logs.logger import logger

from brain.action import Action
from brain.providers.gemini_provider import GeminiProvider


class Processor:

    def __init__(self):

        logger.info("Initializing Processor...")

        self.provider = GeminiProvider()

    def process(self, message: str) -> Action:

        logger.info(f"Processing: {message}")

        try:

            decision = self.provider.chat(message)

            logger.info("Successfully received AI response.")

            return Action.from_dict(decision)

        except Exception as e:

            logger.exception(f"Processor Error: {e}")

            return Action(
                type="chat",
                response="Sorry, I ran into an internal error while processing your request."
            )