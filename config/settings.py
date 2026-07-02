import os
from dotenv import load_dotenv

load_dotenv()

APP_NAME = os.getenv("APP_NAME", "Mike")

VERSION = "1.0"

DEBUG = True

DEFAULT_BROWSER = os.getenv(
    "DEFAULT_BROWSER",
    "Opera"
)

WAKE_WORD = os.getenv(
    "WAKE_WORD",
    "Hey Mike"
)

GEMINI_API_KEY = os.getenv(
    "AQ.Ab8RN6LYAF0aFtIqXeAzMujHxXBw9gfUrT2twekv9ViQAf3o1g"
)