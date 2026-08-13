# Configuration settings for the Mike application
import os
from pathlib import Path
from dotenv import load_dotenv

# Always load the .env from the project root
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"

load_dotenv(dotenv_path=ENV_FILE)

APP_NAME = os.getenv("APP_NAME", "Mike")

VERSION = "1.0"
DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")

DEFAULT_BROWSER = os.getenv("DEFAULT_BROWSER", "Opera")
WAKE_WORD = os.getenv("WAKE_WORD", "Hey Mike")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-2.5-flash"
)

OPENROUTER_MODEL = os.getenv(
    "OPENROUTER_MODEL",
    "qwen/qwen3-235b-a22b"
)

GROQ_MODEL = os.getenv(
    "GROQ_MODEL",
    "llama-3.3-70b-versatile"
)
