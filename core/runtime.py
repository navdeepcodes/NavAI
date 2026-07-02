from logs.logger import logger

from core.conversation import Conversation
from tools.registry import execute


class Runtime:

    def __init__(self):

        logger.info("Initializing Runtime...")

        self.conversation = Conversation()

    def process(self, message: str):

        logger.info(f"Received: {message}")

        try:

            response = self.conversation.send(message)

            # Temporary debug output

            return response

        except Exception as e:

            logger.exception(e)

            raise