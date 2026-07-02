from google import genai
from google.genai import types

from config.settings import GEMINI_API_KEY
from brain.prompts import SYSTEM_PROMPT
from tools.registry import TOOLS

from logs.logger import logger


class Conversation:

    def __init__(self):

        logger.info("Initializing Conversation...")

        self.client = genai.Client(
            api_key=GEMINI_API_KEY
        )

        self.chat = self.client.chats.create(
            model="gemini-2.5-flash",
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=TOOLS,
            )
        )

    def send(self, message: str):

        logger.info(f"User: {message}")

        response = self.chat.send_message(message)

        return response