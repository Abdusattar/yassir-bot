import asyncio
import random
import logging
import aiohttp
from datetime import datetime
import pytz

from config import OR_API_KEY, OR_URL, AI_MODEL, TZ, PROFILE
from core.i18n import lang_instruction
from core.db import get_student_memory, save_chat
from core.content import PROJECT_INFO

log = logging.getLogger(__name__)

_IS_FEMALE = PROFILE == "female"

_HUMAN_STYLE = (
    "STYLE: write like a real person in Telegram, not like an AI. "
    "Plain text only — no bullet points (- • *), no numbered lists, no headers, no **bold** or _italic_. "
    "At most 1-2 emojis total, only if natural. "
    "Short natural sentences, like a teacher typing on a phone."
)


def _g(m: str, f: str) -> str:
    """Выбирает мужскую или женскую форму в зависимости от профиля бота."""
    return f if _IS_FEMALE else m


_GENDER_ADDR = (
    f"Группа {'женская' if _IS_FEMALE else 'мужская'} — только один пол. "
    f"Обращение к одному: «{_g('Брат [имя]', 'Сестра [имя]')}». "
    f"К нескольким: «{_g('Братья', 'Сёстры')}». "
    f"ЗАПРЕЩЕНО писать «братья и сёстры» — группа {'женская' if _IS_FEMALE else 'мужская'}."
)

_MOTIVATIONAL_SYSTEM = (
    "Ты пишешь насыха (наставление) для студентов, заучивающих Коран, "
    "в стиле учёных и таалибуль-'ильм: искренне, тепло, используя переданный аят "
    "и хадис как основу. "
    "Голос бота свободен: приветствие, ободрение студента, связь переданного смысла "
    "с его трудом — в своих словах. "
    "Запрещено только: приписывать Аллаху или Пророку ﷺ что-либо сверх переданного "
    "смысла; придумывать выражения вроде «небо открыто», «день благословлён на аяты». "
    "Арабский и английский текст в сообщении не писать — только перевод смысла.\n\n"
    "АДАБ ОБРАЩЕНИЯ: пиши как мусульманский устаз к своему студенту — тепло, но с достоинством. "
    "Приветствие только исламское: «Ассаляму алейкум», «БаракАллаху фийк», «МашааАллах». "
    + _GENDER_ADDR + " "
    "Никакого светского панибратства: уменьшительно-ласкательных прозвищ, "
    "фамильярных выражений, неисламских приветствий. "
    "Для ду'а — только 🤲, не 🙏."
)


async def _or_call(messages, max_tokens=1024, retries=3):
    """Базовый вызов OpenRouter API (OpenAI-совместимый формат)."""
    headers = {
        "Authorization": "Bearer " + OR_API_KEY,
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/Abdusattar/yassir-bot",
    }
    data = {
        "model": AI_MODEL,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    for attempt in range(retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    OR_URL, headers=headers, json=data,
                    timeout=aiohttp.ClientTimeout(total=45)
                ) as resp:
                    result = await resp.json()
                    if "error" in result:
                        log.warning("OR error (attempt %d): %s", attempt + 1, result.get("error"))
                        if attempt < retries - 1:
                            await asyncio.sleep(3)
                            continue
                        return None
                    return result["choices"][0]["message"]["content"].rstrip() + " ·"
        except Exception as e:
            log.error("OR error (attempt %d): %s", attempt + 1, e)
            if attempt < retries - 1:
                await asyncio.sleep(3)
    return None


async def ask_ai(prompt, system="", retries=3, max_tokens=1024):
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return await _or_call(messages, max_tokens=max_tokens, retries=retries)


async def ask_ai_messages(messages, system="", retries=3):
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.extend(messages)
    return await _or_call(msgs, retries=retries)


# ── Классификация ─────────────────────────────────────────────────────────────

async def classify_message(text, group_tasks):
    """Определяет тип сообщения и выполненные задания.
    Возвращает dict: {type: 'report'|'question'|'chat', tasks: {...}}"""
    task_descriptions = {
        "m": "Заучивание (хифз, 40+40, 20+20, этап, прочитано N раз, выучил наизусть)",
        "r": "Повторение (мураджаа, повторил, закрепил, 'повторил слова', 'забытых слов нет')",
        "t": "Слова/Перевод (муфрадат, новые слова с переводом, 'новые слова: ...')",
        "j": "Таджвид (арабские буквы ق ك غ, звуки, правила чтения, махрадж)",
        "n": "Нахв (арабская грамматика, разбор предложения, харф+исм, фиаль)",
        "h": "Хадис (текст хадиса, слова Пророка)"
    }
    active = "\n".join("- " + k + ": " + task_descriptions[k] for k in group_tasks if k in task_descriptions)
    prompt = (
        "Ты ассистент учителя Корана. Студенты в группе пишут сообщения. "
        "Определи ТИП сообщения и какие задания выполнены.\n\n"
        "ТИПЫ:\n"
        "1. report — СДАЧА УРОКА. Признаки: пункты списком (1. 2. 3.), арабский текст Корана, числа ('40 открыто', '20+20'), слова 'повторил', 'выучил', 'заучил', 'этап', 'забытые слова', 'новые слова', арабские слова с переводом\n"
        "2. question — ВОПРОС: есть '?', слова 'почему/как/что это/не понял', обращение 'Ясир/Yassir'\n"
        "3. chat — приветствие, благодарность, короткая реплика, эмодзи\n\n"
        "Задания (что можно сдать):\n" + active + "\n\n"
        "ПРАВИЛА засчитывания заданий в report:\n"
        "- '40 открыто', 'этап', 'прочитал N раз', 'заучил', 'выучил' → m\n"
        "- 'повторил', 'мураджаа', 'закрепил' → r\n"
        "- 'новых слов нет', 'забытые слова', 'слова', 'муфрадат', арабские слова с переводом → t\n"
        "- арабские буквы/звуки, таджвид → j\n"
        "- грамматика, нахв, разбор → n\n"
        "- хадис → h\n"
        "Засчитывай задание ДАЖЕ если написано кратко. Лучше засчитать чем пропустить.\n\n"
        "ПРИМЕРЫ (учись на них):\n"
        "- 'Заучивание 40+40' → report|m\n"
        "- '1 этап 40/40' → report|m\n"
        "- 'Повторил' → report|r\n"
        "- 'Новые слова' → report|t\n"
        "- 'Забытые слова нет' → report|t\n"
        "- 'глубоко горловая буква ج' → report|j\n"
        "- 'Заучивание Повторение Слова' → report|m,r,t\n"
        "- 'Ясир как будет богобоязненный' → question|\n"
        "- 'Ассаляму алейкум' → chat|\n"
        "- '16/06' (просто дата) → chat|\n\n"
        "Сообщение: \"" + text + "\"\n\n"
        "Ответь ОДНОЙ строкой строго в формате ТИП|буквы:\n"
        "report|m,r,t\n"
        "question|\n"
        "chat|\n"
        "Без пояснений, только одна строка."
    )
    result = await ask_ai(prompt)
    if not result:
        return None
    result = result.strip().lower().split("\n")[0]
    if "|" not in result:
        return None
    msg_type, tasks_str = result.split("|", 1)
    found = {}
    for k in group_tasks:
        if k in tasks_str:
            found[k] = True
    return {"type": msg_type.strip(), "tasks": found}


async def parse_report(text, group_tasks):
    """Распознаёт выполненные задания через ИИ. Возвращает dict {ключ: True} или None."""
    task_descriptions = {
        "m": "Заучивание (хифз, 40+40, 20+20, выучил наизусть, этап заучивания, номера аятов/строк)",
        "r": "Повторение (мурожаа, повторил, закрепил пройденное)",
        "t": "Слова/Перевод (муфрадат, перевод слов, значения, новые слова с переводом)",
        "j": "Таджвид (правила чтения, ОТДЕЛЬНЫЕ АРАБСКИЕ БУКВЫ типа ق ك غ ض ج, харфы, махрадж, места выхода букв)",
        "n": "Нахв (арабская грамматика, разбор предложений, грамматические правила)",
        "h": "Хадис (изучил хадис, текст хадиса, слова Пророка)"
    }
    active = "\n".join("- " + k + ": " + task_descriptions[k] for k in group_tasks if k in task_descriptions)
    prompt = (
        "Студент сдаёт отчёт по урокам Корана. Определи какие задания он выполнил.\n\n"
        "ВАЖНЫЕ ПОДСКАЗКИ:\n"
        "- 'этап', 'прочитано N раз', '40+40', '20+20' = ЗАУЧИВАНИЕ (m)\n"
        "- 'повторение', 'повторил', 'мурожаа', 'мураджаа' = ПОВТОРЕНИЕ (r)\n"
        "- 'новых слов нет', 'забытых слов нет', 'слова повторил', 'муфрадат' = СЛОВА (t)\n"
        "- отдельные АРАБСКИЕ БУКВЫ (ق ك غ ض) или звуки = ТАДЖВИД (j)\n"
        "- арабская грамматика, разбор = НАХВ (n)\n"
        "- хадис, слова Пророка = ХАДИС (h)\n\n"
        "Возможные задания:\n" + active + "\n\n"
        "Текст отчёта: \"" + text + "\"\n\n"
        "Ответь ТОЛЬКО буквами выполненных заданий через запятую, без пробелов. "
        "Например: m,r,t\n"
        "Если ничего не выполнено или это просто разговор — ответь: нет"
    )
    result = await ask_ai(prompt)
    if not result:
        return None
    result = result.strip().lower()
    if "нет" in result or not result:
        return None
    found = {k: True for k in group_tasks if k in result}
    return found if found else None


# ── ИИ-проверка отчёта ────────────────────────────────────────────────────────

async def check_report(name, tasks_done, lang="ru", hadith=None, ayah=None):
    all_done = len(tasks_done) >= 3
    source_block = await _build_source_block(hadith, ayah, lang)
    prompt = (
        "A Quran student named *" + name + "* submitted their daily report.\n"
        "Completed tasks: " + ", ".join(tasks_done) + "\n"
        "All tasks done: " + ("YES!" if all_done else "no, partial") + "\n\n"
        "Do NOT invent details not in the report! "
        "If '40+40' is mentioned — it means the memorization method, do NOT say 'memorized 80 verses'.\n\n"
        + source_block
        + _HUMAN_STYLE + "\n\n"
        "Write: 'BarakAllahu fik, " + name + "!' — brief praise for the tasks — "
        + ("mention the meaning of the ayah/hadith above with its reference — " if source_block else "")
        + ("say they completed everything." if all_done else "gently encourage to finish.") + "\n"
        + lang_instruction(lang) + " Total: 3-4 lines."
    )
    return await ask_ai(prompt, system=_MOTIVATIONAL_SYSTEM)


async def answer_question(question, program_info, group_title, phone=None, group_id=None, student_name=""):
    system = (
        "Ты ИИ-помощник учителя Корана по имени Ясир. Работаешь в Telegram-группе проекта Яссир.\n"
        "Отвечай на основании Корана, хадисов, слов учёных. В вопросах методики — "
        "строго по системе проекта Яссир описанной ниже.\n\n"
        + _HUMAN_STYLE + "\n\n"
        "Кратко и по делу, без воды. Простой язык понятный студенту. "
        "Аяты/хадисы — кратко с источником. "
        "Если студент написал перевод/таджвид/грамматику — проверь и укажи ошибки кратко. "
        "Если всё верно — просто скажи что верно. "
        "На вопросы о фетвах (халяль/харам/фикх) — не отвечай сам, направь к устазу.\n\n"
        "ЯЗЫК ОТВЕТА: отвечай на том же языке на котором задан вопрос.\n\n"
        + PROJECT_INFO + "\n\n"
        "АКАДЕМИЧЕСКИЙ СПРАВОЧНИК (таджвид, нахв, методика):\n" + program_info
    )

    messages = []
    if phone and group_id:
        for h in get_student_memory(phone, group_id):
            messages.append({"role": h["role"], "content": h["content"]})
    name_prefix = ("Студент " + student_name + ": ") if student_name else ""
    messages.append({"role": "user", "content": name_prefix + question})

    result = await ask_ai_messages(messages, system=system)
    if result and phone and group_id:
        save_chat(phone, group_id, "user", question)
        save_chat(phone, group_id, "assistant", result)
    return result or (
        "Ассаляму алейкум! Не могу ответить прямо сейчас.\n"
        "Задай вопрос через несколько минут, или Устаз ответит лично. БаракАллаху фийк! 🕌"
    )


async def answer_ustaz_question(question, program_info, ustaz_name=""):
    system = (
        "You are Yassir — an AI assistant for Quran teachers (ustaz) of the Yassir project.\n"
        "Answer questions about the project methodology, student management, bot commands, and Islamic studies.\n"
        "Base answers strictly on the project info below.\n\n"
        "RESPONSE RULES:\n"
        "- Answer in the same language the question is asked in.\n"
        "- Be concise and clear — the reader is a teacher, not a student.\n"
        "- If the question is about bot settings, technical setup, or something outside your knowledge → "
        "say: 'Это нужно уточнить у супер-админов (Абдусаттар или Умар).'\n"
        "- Do not guess or make up answers. If uncertain → redirect to super admins.\n\n"
        + PROJECT_INFO + "\n\n"
        "ACADEMIC REFERENCE:\n" + program_info
    )
    name_prefix = ("Устаз " + ustaz_name + ": ") if ustaz_name else ""
    result = await ask_ai(name_prefix + question, system=system)
    return result or "Уточните этот вопрос у супер-админов (Абдусаттар или Умар). 🕌"


# ── Планировщик / мотивация ───────────────────────────────────────────────────

async def reminder(name, missed_tasks, day, lang="ru", hadith=None, ayah=None):
    tasks_str = ", ".join(missed_tasks)
    if day == 1:
        urgency, tone = "missed yesterday", "gentle reminder"
    elif day <= 3:
        urgency, tone = str(day) + " days in a row missed", "caring, emphasize importance of consistency"
    elif day <= 7:
        urgency, tone = str(day) + " days in a row missed", "firm, about losing memorization"
    else:
        urgency, tone = str(day) + " days in a row missed", "like an older sibling, about responsibility before Allah"
    source_block = await _build_source_block(hadith, ayah, lang)
    prompt = (
        _HUMAN_STYLE + "\n\n"
        "Write a reminder for Quran student «" + name + "».\n"
        "Situation: " + urgency + ". Missed tasks: " + tasks_str + ". Tone: " + tone + ".\n"
        + source_block
        + "Start with 'Assalamu alaykum, " + name + "!', "
        + ("mention the meaning of the ayah/hadith above with its reference, " if source_block else "")
        + "a brief dua.\n"
        + lang_instruction(lang) + " Length: 5-7 lines."
    )
    return await ask_ai(prompt, system=_MOTIVATIONAL_SYSTEM) or "📖 Assalamu alaykum, " + name + "! Don't forget to submit your report, inshAllah."


async def _get_hadith_translation(hadith: dict, lang: str) -> str:
    """Возвращает перевод хадиса на целевой язык (из кеша или генерирует)."""
    import core.sampler as sampler
    cached = sampler.get_cached_translation(hadith["id"], lang)
    if cached:
        return cached
    english = hadith.get("english_text") or ""
    if not english:
        return ""
    result = await ask_ai(
        "Translate the following hadith narration into " + lang + " (only the translation, no extra text):\n\n" + english,
        max_tokens=300,
    )
    if result:
        text = result.strip().rstrip(" ·")
        sampler.save_translation(hadith["id"], lang, text)
        return text
    return english


async def _get_ayah_translation(ayah: dict, lang: str) -> str:
    """Возвращает перевод аята на целевой язык (из кеша или генерирует)."""
    import core.sampler as sampler
    sura = int(ayah["sura"])
    aya  = int(ayah["aya"])
    cached = sampler.get_cached_ayah_translation(sura, aya, lang)
    if cached:
        return cached
    arabic = ayah.get("arabic", "")
    if not arabic:
        return ""
    result = await ask_ai(
        f"Translate this Quran ayah (Surah {sura}, Ayah {aya}) into {lang}.\n"
        f"Arabic text: {arabic}\n"
        "Provide ONLY the translation — no introduction, no Arabic, no transliteration, no footnotes.",
        max_tokens=200,
    )
    if result:
        text = result.strip().rstrip(" ·")
        sampler.save_ayah_translation(sura, aya, lang, text)
        return text
    return ""


async def _build_source_block(hadith: dict | None, ayah: dict | None, lang: str) -> str:
    """Формирует блок с аятом/хадисом для передачи в промпт DeepSeek."""
    block = ""
    if ayah:
        meaning = ayah.get("meaning_en") or await _get_ayah_translation(ayah, lang)
        block += (
            "АЯТ (используй только смысл — арабский текст в сообщении не писать):\n"
            "Смысл: " + meaning + "\n"
            "Ссылка: (Сура " + str(ayah["sura"]) + ", аят " + str(ayah["aya"]) + ")\n\n"
        )
    if hadith:
        translation = await _get_hadith_translation(hadith, lang) if lang != "ar" else ""
        english = (hadith.get("english_text") or "").strip()
        hadith_meaning = (translation or english).strip()
        block += (
            "ХАДИС (используй только смысл — арабский и английский текст не писать):\n"
            "Смысл: " + hadith_meaning + "\n"
            "Ссылка: ("
            + hadith.get("label", hadith.get("collection", ""))
            + ", №" + str(hadith.get("hadith_number", "")) + ")\n\n"
        )
    return block


async def group_motivation(missing_names, group_title, lang="ru",
                           gtype="relaxed", hadith=None, ayah=None):
    names_str = ", ".join(missing_names) if missing_names else ""

    source_block = ""
    if ayah:
        meaning = ayah.get("meaning_en") or await _get_ayah_translation(ayah, lang)
        source_block += (
            "АЯТ (используй только смысл — арабский текст в сообщении не писать):\n"
            "Смысл: " + meaning + "\n"
            "Ссылка: (Сура " + ayah["sura"] + ", аят " + ayah["aya"] + ")\n\n"
        )
    if hadith:
        translation = await _get_hadith_translation(hadith, lang) if lang != "ar" else ""
        english = (hadith.get("english_text") or "").strip()
        hadith_meaning = (translation or english).strip()
        source_block += (
            "ХАДИС (используй только смысл — арабский и английский текст не писать):\n"
            "Смысл: " + hadith_meaning + "\n"
            "Ссылка: ("
            + hadith.get("label", hadith.get("collection", ""))
            + ", №" + str(hadith.get("hadith_number", "")) + ")\n\n"
        )

    if gtype == "pro":
        tone_instr = (
            "Тон: собранный, мотивирующий. Группа с строгим расписанием хифза. "
            "Акцент на постоянстве и ответственности перед Аллахом."
        )
    else:
        tone_instr = (
            "Тон: тёплый, мягкий, вдохновляющий. Группа занимается в своём темпе. "
            "Акцент на милости Аллаха к тем, кто занимается Его Книгой."
        )

    system = (
        "Ты пишешь насыха (наставление) для студентов, заучивающих Коран, "
        "в стиле учёных и таалибуль-'ильм: искренне, тепло, используя переданный аят "
        "и хадис как основу. "
        "Голос бота свободен: ободрить студентов, связать переданный смысл с их трудом "
        "в своих словах. "
        "Запрещено только: приписывать Аллаху или Пророку ﷺ что-либо сверх переданного "
        "смысла; придумывать выражения вроде «небо открыто», «день благословлён на аяты». "
        "Арабский и английский текст в сообщении не писать — только перевод смысла. "
        + _GENDER_ADDR
    )

    prompt = (
        _HUMAN_STYLE + "\n\n"
        "Напиши утреннее мотивационное сообщение для группы «" + group_title + "».\n"
        + ("Студенты, не сдавшие сегодня: " + names_str + ".\n" if names_str else "")
        + "\n"
        + source_block
        + tone_instr + "\n\n"
        "ПРАВИЛА ОФОРМЛЕНИЯ:\n"
        "- После упоминания смысла аята сразу в скобках: (Сура N, аят M)\n"
        "- После упоминания смысла хадиса сразу в скобках: (Сборник, №N)\n"
        "- Арабский и английский текст не включать.\n"
        "- Смысл аята/хадиса цитируй точно с ссылкой; можно своими словами связать его с трудом студентов — нельзя приписывать Аллаху/Пророку ﷺ больше переданного.\n"
        "- Структура: 1) насыха от бота — тёплые слова студентам; 2) смысл аята/хадиса с ссылкой как опора; 3) связь с трудом в словах бота; 4) ду'а.\n"
        + ("- Обратиться к студентам по именам и призвать сдать сегодня.\n" if names_str else "")
        + lang_instruction(lang) + " Длина: 5-7 строк."
    )
    return await ask_ai(prompt, system=system)


# ── Закрывающие строки по языкам (добавляются механически после base-текста) ──

SUBMIT_TODAY = {
    "ru": "— сдайте сегодня, ин ша Аллах! 🤲",
    "ky": "— бүгүн тапшырыңыздар, ин ша Аллах! 🤲",
    "uz": "— bugun topshiring, in sha Alloh! 🤲",
    "kk": "— бүгін тапсырыңыздар, ин ша Аллах! 🤲",
    "tr": "— bugün teslim edin, inşallah! 🤲",
    "ar": "— سلّموا اليوم، إن شاء الله! 🤲",
    "en": "— submit today, inshAllah! 🤲",
}


async def group_motivation_base(lang: str, gtype: str,
                                hadith=None, ayah=None) -> str | None:
    """Насыха без имён. Один вызов на (gtype, lang); имена добавляет планировщик."""
    source_block = ""
    if ayah:
        meaning = ayah.get("meaning_en") or await _get_ayah_translation(ayah, lang)
        source_block += (
            "АЯТ (используй только смысл — арабский текст в сообщении не писать):\n"
            "Смысл: " + meaning + "\n"
            "Ссылка: (Сура " + ayah["sura"] + ", аят " + ayah["aya"] + ")\n\n"
        )
    if hadith:
        translation = await _get_hadith_translation(hadith, lang) if lang != "ar" else ""
        english = (hadith.get("english_text") or "").strip()
        hadith_meaning = (translation or english).strip()
        source_block += (
            "ХАДИС (используй только смысл — арабский и английский текст не писать):\n"
            "Смысл: " + hadith_meaning + "\n"
            "Ссылка: ("
            + hadith.get("label", hadith.get("collection", ""))
            + ", №" + str(hadith.get("hadith_number", "")) + ")\n\n"
        )

    if gtype == "pro":
        tone_instr = (
            "Тон: собранный, мотивирующий. Группа с строгим расписанием хифза. "
            "Акцент на постоянстве и ответственности перед Аллахом."
        )
    else:
        tone_instr = (
            "Тон: тёплый, мягкий, вдохновляющий. Группа занимается в своём темпе. "
            "Акцент на милости Аллаха к тем, кто занимается Его Книгой."
        )

    system = (
        "Ты пишешь насыха (наставление) для студентов, заучивающих Коран, "
        "в стиле учёных и таалибуль-'ильм: искренне, тепло, используя переданный аят "
        "и хадис как основу. "
        "Голос бота свободен: ободрить студентов, связать переданный смысл с их трудом "
        "в своих словах. "
        "Запрещено только: приписывать Аллаху или Пророку ﷺ что-либо сверх переданного "
        "смысла; придумывать выражения вроде «небо открыто», «день благословлён на аяты». "
        "Арабский и английский текст в сообщении не писать — только перевод смысла. "
        + _GENDER_ADDR
    )

    prompt = (
        _HUMAN_STYLE + "\n\n"
        "Напиши мотивационное насыха для студентов, заучивающих Коран.\n"
        "Не обращайся по именам — только общий текст.\n\n"
        + source_block
        + tone_instr + "\n\n"
        "ПРАВИЛА ОФОРМЛЕНИЯ:\n"
        "- После упоминания смысла аята сразу в скобках: (Сура N, аят M)\n"
        "- После упоминания смысла хадиса сразу в скобках: (Сборник, №N)\n"
        "- Арабский и английский текст не включать.\n"
        "- Смысл аята/хадиса цитируй точно с ссылкой; можно своими словами связать его с трудом студентов — нельзя приписывать Аллаху/Пророку ﷺ больше переданного.\n"
        "- Структура: 1) насыха от бота — тёплые слова студентам; 2) смысл аята/хадиса с ссылкой как опора; 3) связь с трудом в словах бота; 4) ду'а.\n"
        "- Завершай мягким общим напоминанием, без призыва по именам.\n"
        + lang_instruction(lang) + " Длина: 4-6 строк."
    )
    return await ask_ai(prompt, system=system)


async def personal_streak_praise(name, streak_days, lang="ru", hadith=None, ayah=None):
    source_block = await _build_source_block(hadith, ayah, lang)
    prompt = (
        _HUMAN_STYLE + "\n\n"
        "Write a congratulation for Quran student «" + name + "» — "
        + str(streak_days) + " days in a row without missing!\n"
        + source_block
        + "Start with 'Assalamu alaykum, " + name + "! MashaAllah!', congratulate, "
        + ("mention the meaning of the ayah/hadith above with its reference, " if source_block else "")
        + "a dua.\n"
        + lang_instruction(lang) + " Length: 5-7 lines."
    )
    return await ask_ai(prompt, system=_MOTIVATIONAL_SYSTEM)


async def praise_completed(name, lang="ru", hadith=None, ayah=None):
    source_block = await _build_source_block(hadith, ayah, lang)
    prompt = (
        _HUMAN_STYLE + "\n\n"
        "Write warm praise for Quran student «" + name + "» who completed ALL tasks TODAY.\n"
        + source_block
        + "Start with 'BarakAllahu fik, " + name + "!', praise their dedication, "
        + ("mention the meaning of the ayah/hadith above with its reference, " if source_block else "")
        + "a brief dua.\n"
        + lang_instruction(lang) + " Tone: joyful, sincere. Length: 4-6 lines."
    )
    return await ask_ai(prompt, system=_MOTIVATIONAL_SYSTEM)


async def absent_motivation(name, days, lang="ru", hadith=None, ayah=None):
    source_block = await _build_source_block(hadith, ayah, lang)
    prompt = (
        _HUMAN_STYLE + "\n\n"
        "Quran student «" + name + "» has not submitted a report for " + str(days) + " days.\n"
        + source_block
        + "Write a gentle warm reminder (do NOT scold!): address them by name with warmth, "
        "say they are missed, invite them to return, "
        + ("mention the meaning of the ayah/hadith above with its reference, " if source_block else "")
        + "a brief dua.\n"
        + lang_instruction(lang) + " Tone: kind, no blame. 3-4 lines."
    )
    return await ask_ai(prompt, system=_MOTIVATIONAL_SYSTEM)


async def winner_praise(name, period_label, points, lang="ru", hadith=None, ayah=None):
    source_block = await _build_source_block(hadith, ayah, lang)
    prompt = (
        _HUMAN_STYLE + "\n\n"
        "Write a congratulation for Quran student «" + name + "» — "
        "top student of the " + period_label + " with " + str(points) + " points!\n"
        + source_block
        + "Start with 'MashaAllah, " + name + "!', congratulate on first place, "
        + ("mention the meaning of the ayah/hadith above with its reference, " if source_block else "")
        + "a brief dua.\n"
        + lang_instruction(lang) + " Short and warm: 3-4 lines."
    )
    return await ask_ai(prompt, system=_MOTIVATIONAL_SYSTEM)


async def group_praise(names, lang="ru", hadith=None, ayah=None):
    names_str = ", ".join(names)
    source_block = await _build_source_block(hadith, ayah, lang)
    prompt = (
        _HUMAN_STYLE + "\n\n"
        "Write group praise for Quran students who completed all tasks TODAY: " + names_str + ".\n"
        + source_block
        + "Start with 'MashaAllah! TabarakAllah!', list the names and praise them, "
        + ("mention the meaning of the ayah/hadith above with its reference, " if source_block else "")
        + "a dua for all.\n"
        + lang_instruction(lang) + " Tone: inspiring. Length: 5-7 lines."
    )
    return await ask_ai(prompt, system=_MOTIVATIONAL_SYSTEM)


async def warning_skips(name, skip_count, lang="ru", hadith=None, ayah=None):
    source_block = await _build_source_block(hadith, ayah, lang)
    prompt = (
        _HUMAN_STYLE + "\n\n"
        "Write a serious warning for Quran student «" + name + "».\n"
        "Situation: " + str(skip_count) + " missed days this month, "
        + str(14 - skip_count) + " days left before transfer to Tadabbur group.\n"
        + source_block
        + "Start with 'Assalamu alaykum, " + name + "!', warn about the transfer, "
        + ("mention the meaning of the ayah/hadith above with its reference, " if source_block else "")
        + "a call to return.\n"
        + lang_instruction(lang) + " Tone: serious but not harsh. 4-6 lines."
    )
    return await ask_ai(prompt, system=_MOTIVATIONAL_SYSTEM)


async def ask_admin_improvement(groups):
    group_titles = ", ".join(g["title"] for g in groups) if groups else "no groups"
    prompt = (
        "You are AI assistant Yassir.\n"
        "Groups: " + group_titles + "\n"
        "Ask the Ustaz ONE question to better help students.\n"
        "Start with 'Ustaz, I want to improve...'\n"
        "Language: Russian. Length: 3-4 lines."
    )
    return await ask_ai(prompt)


async def mystats_comment(name, streak, rank, total_score, days_done, lang="ru"):
    prompt = (
        "Write a brief motivational comment for Quran student «" + name + "».\n"
        "Their stats: " + str(streak) + " day streak, rank #" + str(rank) +
        ", total " + str(total_score) + " points over " + str(days_done) + " days.\n"
        "1 sentence of encouragement + 1 dua.\n"
        + lang_instruction(lang) + " Length: 2-3 lines."
    )
    return await ask_ai(prompt)


async def extract_name(text: str) -> str | None:
    """Extracts a person's name from arbitrary user input."""
    result = await ask_ai(
        "The user wrote: «" + text + "»\n"
        "Extract only the person's name. Return ONE word or a few words (the name only) — no extra text.\n"
        "If it is not a name — return: NO",
        system="You are a name extraction assistant. Reply only with the name or the word NO."
    )
    if not result:
        return None
    result = result.strip().strip("«»\"'·—-")
    first_word = result.upper().split()[0].strip("·—-.") if result else ""
    if first_word in ("НЕТ", "NET", "NO", "NONE") or not result:
        return None
    if len(result) > 50:
        return None
    return result


async def is_valid_name(name: str) -> bool:
    """Checks if the extracted string is actually a real person's name."""
    result = await ask_ai(
        "Is «" + name + "» a real person's name (first name or full name)? "
        "Reply only YES or NO.",
        system="You are a name validation assistant. Reply only YES or NO."
    )
    if not result:
        return True  # сомнения — пропускаем, не блокируем
    return result.strip().upper().startswith("YES")
