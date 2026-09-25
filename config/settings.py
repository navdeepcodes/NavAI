# Configuration settings for the Mike application
import os
from pathlib import Path
from dotenv import load_dotenv

# Always load the .env from the project root
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"

load_dotenv(dotenv_path=ENV_FILE)

APP_NAME = os.getenv("APP_NAME", "Mike")

VERSION = "1.0.0"
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

# ── Publishing ────────────────────────────────────────────────
# Who ships Mike and where people find help. Shown in Settings → About and
# filled into the Privacy Policy and Terms (docs/legal/*.md, {placeholders}).
# SUPPORT_EMAIL is deliberately empty until there is a real inbox behind it:
# the app hides the "Email support" link rather than show an address nobody
# reads.
PUBLISHER = "Huddlecode"
WEBSITE = "https://huddlecode.com"
SUPPORT_EMAIL = ""
#: Bump when the Privacy Policy or Terms change materially; people are asked
#: to accept the new version on their next launch.
LEGAL_VERSION = "2026-09-25.2"  # .2: Mike accounts

# ── Accounts (Supabase) ───────────────────────────────────────
# Optional Mike accounts: email, name and photo, synced across computers.
# Conversations, memory and files never leave the computer either way.
# Accounts stay switched off — and hidden — until both values are set. The
# project URL and its public key (the "anon" or "publishable" key, never the
# service-role / secret key) are safe to ship in the app: row-level security
# in supabase/migrations decides what anyone can do. Setup: docs/ACCOUNTS.md.
SUPABASE_URL = os.getenv("MIKE_SUPABASE_URL", "https://ljvvkiaikosvznedzanx.supabase.co")
SUPABASE_ANON_KEY = os.getenv(
    "MIKE_SUPABASE_ANON_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxqdnZraWFpa29zdnpu"
    "ZWR6YW54Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTAyOTYzMDEsImV4cCI6MjEwNTg3MjMwMX0.kupHNFSOjH2L3_"
    "D4vKe3bARZODmMWJRWd_StRgTY6rI",
)
#: Sign-in providers switched on in the Supabase project, e.g. "google".
SUPABASE_OAUTH_PROVIDERS = [
    p.strip() for p in os.getenv("MIKE_SUPABASE_OAUTH", "").split(",") if p.strip()
]
#: True makes Mike usable only when signed in. Off: an account is optional,
#: offered once on first run and always available in Settings → Account.
ACCOUNT_REQUIRED = os.getenv("MIKE_ACCOUNT_REQUIRED", "").lower() in ("1", "true", "yes")
