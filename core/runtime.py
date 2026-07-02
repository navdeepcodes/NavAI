from logs.logger import logger

from core.conversation import Conversation


class Runtime:

    def __init__(self):

        logger.info("Initializing Runtime...")

        self.conversation = Conversation()

    def process(self, message: str):

        logger.info(f"Received: {message}")

        response = self.conversation.send(message)

        return response