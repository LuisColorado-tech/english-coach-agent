"""
Global project configuration.
Loads from .env and provides constants used across the project.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
load_dotenv(PROJECT_ROOT / ".env")

# === Paths ===
DATA_DIR = Path(os.environ.get("ECA_DATA_DIR", PROJECT_ROOT / "data"))
LOGS_DIR = PROJECT_ROOT / "logs"
PROFILE_PATH = DATA_DIR / "profile.json"
DB_PATH = DATA_DIR / "sessions.db"

# === DeepSeek API ===
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_TEMPERATURE = 0.8
DEEPSEEK_MAX_TOKENS = 500
DEEPSEEK_MAX_HISTORY_TURNS = 20
DEEPSEEK_RETRY_ATTEMPTS = 3
DEEPSEEK_RETRY_BACKOFF = [1, 2, 4]

# === STT / Whisper ===
WHISPER_MODEL = os.environ.get("ECA_WHISPER_MODEL", "base.en")
WHISPER_DEVICE = "cpu"
WHISPER_COMPUTE_TYPE = "int8"
STT_CHUNK_SIZE_MS = 300
STT_SILENCE_THRESHOLD_MS = 800
STT_SAMPLE_RATE = 16000

# === VAD ===
VAD_THRESHOLD = 0.3
VAD_FRAME_DURATION_MS = 30

# === TTS ===
TTS_DEFAULT_VOICE = os.environ.get("ECA_TTS_VOICE", "en-US-AriaNeural")
TTS_RATE = "+5%"
TTS_PITCH = "+0Hz"
TTS_VOLUME = "+0%"

# === Spontaneous triggers ===
SPONTANEOUS_ENABLED = os.environ.get("ECA_SPONTANEOUS_ENABLED", "true").lower() == "true"
SPONTANEOUS_MIN_MINUTES = int(os.environ.get("ECA_SPONTANEOUS_MIN_MINUTES", "45"))
SPONTANEOUS_MAX_MINUTES = int(os.environ.get("ECA_SPONTANEOUS_MAX_MINUTES", "120"))
ACTIVE_HOURS_START = 8
ACTIVE_HOURS_END = 22

# === Context ===
MAX_CONTEXT_TOKENS = 2000
RECENT_ERRORS_SESSIONS = 7
MAX_ERRORS_INJECTED = 10

# === UI ===
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 500
UI_ALWAYS_ON_TOP = True
UI_FONT_FAMILY = "Consolas"
UI_FONT_SIZE = 13
UI_THEME = "dark"
UI_COLOR_THEME = "blue"

# === Logging ===
LOG_LEVEL = os.environ.get("ECA_LOG_LEVEL", "INFO")
LOG_ROTATION = "10 MB"
LOG_RETENTION = 5
