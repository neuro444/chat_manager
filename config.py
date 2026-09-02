"""Single control panel for all tuning. Nothing numeric belongs anywhere else."""
import os
from pathlib import Path

from dotenv import load_dotenv

# Anchor everything to the project directory, never the process's cwd — a
# relative DB path silently creates a fresh empty database when the server is
# started from somewhere else, which looks exactly like data loss.
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _int(key, default):
    return int(os.getenv(key, default))


def _float(key, default):
    return float(os.getenv(key, default))


# ── LLM ───────────────────────────────
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-5.6-luna")
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "gpt-5.6-luna")
TEMPERATURE = _float("TEMPERATURE", 0.3)
MAX_TOKENS = _int("MAX_TOKENS", 1500)
MAX_RETRIES = _int("MAX_RETRIES", 3)

# ── Storage ───────────────────────────
STORAGE = os.getenv("STORAGE", "sqlite")
_sqlite_env = os.getenv("SQLITE_PATH", "chat_manager.db")
# Relative values resolve against the project dir, not the cwd.
SQLITE_PATH = str(
    Path(_sqlite_env) if Path(_sqlite_env).is_absolute() else BASE_DIR / _sqlite_env
)
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "chat_manager")

# ── Context budget ────────────────────
MAX_CONTEXT_TOKENS = _int("MAX_CONTEXT_TOKENS", 32000)
RESERVED_FOR_REPLY = _int("RESERVED_FOR_REPLY", 1500)
CHARS_PER_TOKEN = 4
# Encoding used when the model name is not one tiktoken knows. o200k_base is
# the current GPT-4o/5 family encoding.
TIKTOKEN_ENCODING = os.getenv("TIKTOKEN_ENCODING", "o200k_base")
HISTORY_WINDOW = _int("HISTORY_WINDOW", 200)
SUMMARY_TRIGGER_EVERY = _int("SUMMARY_TRIGGER_EVERY", 10)
CROSS_SESSION_WINDOW = _int("CROSS_SESSION_WINDOW", 5)
CROSS_SESSION_SESSION_WINDOW = _int("CROSS_SESSION_SESSION_WINDOW", 5)
CROSS_SESSION_MESSAGE_WINDOW = _int("CROSS_SESSION_MESSAGE_WINDOW", 40)
CARRY_OVER_SCAN_LIMIT = _int("CARRY_OVER_SCAN_LIMIT", 20)

CONTEXT_BUDGET_WEIGHTS = {
    "domain": 0.35,
    "history": 0.30,
    "summary": 0.15,
    "memory": 0.15,
    "profile": 0.05,
}

# ── Debug ─────────────────────────────
DEBUG_CONTEXT = os.getenv("DEBUG_CONTEXT", "false").lower() in ("1", "true", "yes")

# ── Ordering ──────────────────────────
SESSION_TIMEOUT_MINUTES = _int("SESSION_TIMEOUT_MINUTES", 5)
# How long telephony should wait after a call is flagged ended, so TTS can
# finish speaking the sign-off before the line drops. We only report it.
CALL_END_DELAY_SECONDS = _int("CALL_END_DELAY_SECONDS", 20)
TAX_RATE = _float("TAX_RATE", 0.0775)
PICKUP_PREPARATION_MINUTES = os.getenv("PICKUP_PREPARATION_MINUTES", "20-30")

# ── Voice ─────────────────────────────
STT_MODEL = os.getenv("STT_MODEL", "gpt-transcribe")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
# accept either name; ELEVEN_VOICE is what the user set in .env
ELEVENLABS_VOICE_ID = (
    os.getenv("ELEVENLABS_VOICE_ID") or os.getenv("ELEVEN_VOICE") or ""
)
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_v3")

# ── Server ────────────────────────────
HOST = os.getenv("HOST", "127.0.0.1")
PORT = _int("PORT", 8000)

# ── API auth ──────────────────────────
# Two named keys, not one shared secret -- so a route can tell which caller
# it's talking to and scope access accordingly (see api.py). Both use the
# same header name; a caller sends whichever key it was issued.
# TELEPHONY_API_KEY: the telephony gateway sends this on /chat only -- it
# has no legitimate reason to read or delete transcripts.
# DASHBOARD_API_KEY: staff tooling (this repo's own bundled dashboard, and
# voice_central) sends this -- it can reach /chat too (the dashboard has its
# own live chat-test feature) plus every transcript/session/order route.
# Either empty disables auth on the routes it would have guarded, so local
# development and the test suite are unaffected; set both in production.
API_KEY_HEADER = os.getenv("API_KEY_HEADER", "X-API-Key")
TELEPHONY_API_KEY = os.getenv("TELEPHONY_API_KEY", "")
DASHBOARD_API_KEY = os.getenv("DASHBOARD_API_KEY", "")

# ── Call disclosure ───────────────────
# Voice-only (see context/assembler.py). Off by default so existing behavior
# and SYSTEM_PROMPT-based tests are unaffected until explicitly enabled.
DISCLOSURE_ENABLED = os.getenv("DISCLOSURE_ENABLED", "false").lower() in ("1", "true", "yes")
DISCLOSURE_LINE = os.getenv(
    "DISCLOSURE_LINE",
    "This call may be recorded and processed by our ordering assistant.",
)
