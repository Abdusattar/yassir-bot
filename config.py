import os

PROFILE = os.getenv("BOT_PROFILE", "male")  # "male" | "female"
IS_FEMALE = PROFILE == "female"

TELEGRAM_TOKEN = (
    os.getenv(f"TELEGRAM_TOKEN_{PROFILE.upper()}")
    or os.getenv("TELEGRAM_TOKEN", "")
)
TG_API = "https://api.telegram.org/bot" + TELEGRAM_TOKEN

# Telegram user_id суперадминов (числа через запятую в SUPER_ADMIN_IDS)
SUPER_ADMIN_IDS = [s.strip() for s in os.getenv("SUPER_ADMIN_IDS", os.getenv("ADMIN_IDS", "")).split(",") if s.strip()]

# Устаз, которому шлём черновики частей учебной программы (нахв/таджвид) на
# одобрение реакцией 👍 — по умолчанию второй SUPER_ADMIN_ID (устаз Умар).
CURRICULUM_REVIEWER_ID = os.getenv("CURRICULUM_REVIEWER_ID") or (
    SUPER_ADMIN_IDS[1] if len(SUPER_ADMIN_IDS) > 1 else (SUPER_ADMIN_IDS[0] if SUPER_ADMIN_IDS else "")
)

TZ = os.getenv("TZ", "Asia/Bishkek")
DB = os.getenv("DB_PATH", f"quran_{PROFILE}.db")

# OpenRouter API (совместим со старым CLAUDE_API_KEY)
OR_API_KEY = os.getenv("OPENROUTER_API_KEY") or os.getenv("CLAUDE_API_KEY", "")
OR_URL = "https://openrouter.ai/api/v1/chat/completions"
AI_MODEL = os.getenv("AI_MODEL", "deepseek/deepseek-v4-flash")

# Shadow mode: если задан SHADOW_CHAT_IDS — бот не отвечает в группах,
# а пересылает ответы наблюдателям (через запятую: user_id или chat_id)
SHADOW_CHAT_IDS = [s.strip() for s in os.getenv("SHADOW_CHAT_IDS", "").split(",") if s.strip()]

# Группа устазов («Масштабирование») — куда шлём сводные отчёты (голосовые
# проверки, операционные отчёты). Своя для каждого профиля (male/female).
SCALING_CHAT_ID = os.getenv("SCALING_CHAT_ID", "")
SCALING_INVITE_LINK = os.getenv("SCALING_INVITE_LINK", "")
