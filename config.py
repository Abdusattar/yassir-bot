import os

PROFILE = os.getenv("BOT_PROFILE", "male")  # "male" | "female"

TELEGRAM_TOKEN = (
    os.getenv(f"TELEGRAM_TOKEN_{PROFILE.upper()}")
    or os.getenv("TELEGRAM_TOKEN", "")
)
TG_API = "https://api.telegram.org/bot" + TELEGRAM_TOKEN

# Telegram user_id администраторов (числа через запятую в ADMIN_IDS)
ADMIN_PHONES = [s.strip() for s in os.getenv("ADMIN_IDS", "").split(",") if s.strip()]

TZ = os.getenv("TZ", "Asia/Bishkek")
DB = os.getenv("DB_PATH", f"quran_{PROFILE}.db")

# OpenRouter API (совместим со старым CLAUDE_API_KEY)
OR_API_KEY = os.getenv("OPENROUTER_API_KEY") or os.getenv("CLAUDE_API_KEY", "")
OR_URL = "https://openrouter.ai/api/v1/chat/completions"
AI_MODEL = os.getenv("AI_MODEL", "google/gemini-2.0-flash-001")

# Shadow mode: если задан SHADOW_CHAT_IDS — бот не отвечает в группах,
# а пересылает ответы наблюдателям (через запятую: user_id или chat_id)
SHADOW_CHAT_IDS = [s.strip() for s in os.getenv("SHADOW_CHAT_IDS", "").split(",") if s.strip()]
