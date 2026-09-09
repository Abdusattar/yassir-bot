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

# Обязателен ли проход через подготовительную для НОВЫХ (никогда не виденных)
# людей, зашедших сразу в pro/relaxed. По умолчанию включено (мужской бот —
# группы устаканились, в основном новички). Для женского бота временно
# выключить в .env (REQUIRE_PREP_FOR_NEW_STUDENTS=false) — группы только
# мигрировали из WhatsApp, уже сформированы, устазы сами следят за составом;
# включить обратно через ~2 месяца (решение пользователя 25.07.2026).
REQUIRE_PREP_FOR_NEW_STUDENTS = os.getenv("REQUIRE_PREP_FOR_NEW_STUDENTS", "true").lower() == "true"

# Quran Academy Digital Quran API (пословный перевод для тренажёра муфрадата)
QURAN_ACADEMY_ACCESS_TOKEN = os.getenv("QURAN_ACADEMY_ACCESS_TOKEN", "")

# Мусхаф Mini App (28.08.2026) - свой GCP-сервер, nginx; с 07.09.2026 свой
# домен yassirilm.com (Турция резала ddns.net по SNI, см. wiki/infrastructure.md)
MUSHAF_URL = os.getenv("MUSHAF_URL", "https://yassirilm.com/")

# Прямая ссылка на Mini App (07.09.2026): t.me/<бот>/<короткое имя>.
# В ГРУППАХ web_app-кнопка запрещена платформой, а обычная ссылка на сайт
# открывает страницу БЕЗ подписи Telegram - приложение не узнаёт студента и
# работать не может. Прямая ссылка приложения этого ограничения не имеет:
# открывается настоящим Mini App с авторизацией из любого чата. Пусто -
# откатываемся на прежний адрес сайта, чтобы кнопка не пропала совсем.
MUSHAF_APP_LINK = os.getenv("MUSHAF_APP_LINK", "")

# Тренажёр муфрадата в вебе (29.08.2026) - HTTP API живёт в ТОМ ЖЕ процессе,
# что и getUpdates-цикл (asyncio-задача, см. bot.py). Мужской и женский бот -
# два процесса на одном сервере (см. память "Два бота"), поэтому у каждого
# СВОЙ порт (иначе второй процесс не забиндится) - nginx разводит по
# префиксу пути (/api/muf/male/, /api/muf/female/), см. wiki/infrastructure.md.
MUFRADAT_API_PORT = int(os.getenv("MUFRADAT_API_PORT", "8081" if PROFILE == "male" else "8082"))

# OpenRouter API (совместим со старым CLAUDE_API_KEY)
OR_API_KEY = os.getenv("OPENROUTER_API_KEY") or os.getenv("CLAUDE_API_KEY", "")
OR_URL = "https://openrouter.ai/api/v1/chat/completions"
AI_MODEL = os.getenv("AI_MODEL", "deepseek/deepseek-v4-flash")

# Незваный ответ бота на сообщение студента (09.09.2026, выключен решением
# пользователя): когда сообщение не распознано ни как отчёт, ни как узр, бот
# спрашивал ИИ "относится ли это к делу" и, если да, отвечал сам. Слишком
# много непрошеных реплик в группах. Прямое обращение ("Яссир, ...") этим
# флагом НЕ затрагивается - оно работает всегда, как и зачёт заданий.
AI_ANSWER_IF_RELEVANT = os.getenv("AI_ANSWER_IF_RELEVANT", "false").lower() == "true"

# Shadow mode: если задан SHADOW_CHAT_IDS — бот не отвечает в группах,
# а пересылает ответы наблюдателям (через запятую: user_id или chat_id)
SHADOW_CHAT_IDS = [s.strip() for s in os.getenv("SHADOW_CHAT_IDS", "").split(",") if s.strip()]

# Группа устазов («Масштабирование») — куда шлём сводные отчёты (голосовые
# проверки, операционные отчёты). Своя для каждого профиля (male/female).
SCALING_CHAT_ID = os.getenv("SCALING_CHAT_ID", "")
SCALING_INVITE_LINK = os.getenv("SCALING_INVITE_LINK", "")
