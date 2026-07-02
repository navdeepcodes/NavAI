import json

from google import genai

from config.settings import GEMINI_API_KEY
from brain.prompts import SYSTEM_PROMPT
from logs.logger import logger


class GeminiProvider:

    def __init__(self):

        logger.info("Initializing Gemini Provider...")

        self.client = genai.Client(
            api_key=GEMINI_API_KEY
        )

        self.model = "gemini-2.5-flash"

    def chat(self, user_message):

        logger.info("Sending request to Gemini...")

        response = self.client.models.generate_content(

            model=self.model,

            contents=user_message,

            config={
                "system_instruction": SYSTEM_PROMPT,
                "temperature": 0.2,
                "max_output_tokens": 500,
                "response_mime_type": "application/json"
            }

        )

        text = response.text.strip()

        logger.info("Gemini Response:")
        logger.info(text)

        return self.parse_json(text)

    def parse_json(self, text):

        """
        Safely parse Gemini's JSON response.
        """

        try:

            return json.loads(text)

        except json.JSONDecodeError:

            logger.warning("Gemini returned invalid JSON.")

            start = text.find("{")
            end = text.rfind("}")

            if start != -1 and end != -1:

                try:

                    return json.loads(
                        text[start:end + 1]
                    )

                except Exception:

                    pass

            logger.exception("Failed to recover JSON.")

            return {
                "type": "chat",
                "response": "Sorry, I couldn't understand my own response."
            }