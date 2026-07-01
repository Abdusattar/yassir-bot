import asyncio
import random
import logging
import aiohttp
from datetime import datetime
import pytz

from config import OR_API_KEY, OR_URL, AI_MODEL, TZ, PROFILE

_GEMINI_FLASH = "google/gemini-2.5-flash"
_LANG_MODEL   = {"ky": _GEMINI_FLASH}


def _model_for_lang(lang: str) -> str:
    return _LANG_MODEL.get(lang, AI_MODEL)
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


async def _or_call(messages, max_tokens=1024, retries=3, model=None):
    """Базовый вызов OpenRouter API (OpenAI-совместимый формат)."""
    headers = {
        "Authorization": "Bearer " + OR_API_KEY,
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/Abdusattar/yassir-bot",
    }
    data = {
        "model": model or AI_MODEL,
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


async def ask_ai(prompt, system="", retries=3, max_tokens=1024, model=None):
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return await _or_call(messages, max_tokens=max_tokens, retries=retries, model=model)


async def ask_ai_messages(messages, system="", retries=3, model=None):
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.extend(messages)
    return await _or_call(msgs, retries=retries, model=model)


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
    return await ask_ai(prompt, system=_MOTIVATIONAL_SYSTEM, model=_model_for_lang(lang))


async def answer_question(question, program_info, group_title, phone=None, group_id=None, student_name="", is_ustaz=False):
    role_note = (
        "Собеседник — УСТАЗ (администратор группы).\n"
        if is_ustaz else
        "Собеседник — СТУДЕНТ (не устаз, не администратор). "
        "Не называй его устазом. Команды устаза ему не показывай — только студенческие.\n"
    )
    system = (
        "Ты ИИ-помощник учителя Корана по имени Ясир. Работаешь в Telegram-группе проекта Яссир.\n"
        + role_note + "\n"
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


async def answer_if_relevant(question, program_info, group_title, phone=None, group_id=None, student_name="", is_ustaz=False):
    """Отвечает только если сообщение явно адресовано боту. Возвращает None если нет."""
    role_note = (
        "Собеседник — УСТАЗ (администратор группы).\n"
        if is_ustaz else
        "Собеседник — СТУДЕНТ. Не называй его устазом. Команды устаза не показывай.\n"
    )
    system = (
        "Ты ИИ-помощник учителя Корана по имени Ясир. Работаешь в Telegram-группе проекта Яссир.\n"
        + role_note
        + "Студент написал сообщение в группе. СНАЧАЛА определи — обращается ли он К ТЕБЕ (к боту).\n\n"
        "Отвечай ТОЛЬКО если это явный вопрос или запрос к боту: про задания, правила, методику, "
        "команды, расписание, баллы, статистику, арабский язык, Коран, таджвид, нахв, муфрадат.\n\n"
        "ИГНОРИРУЙ (пиши IGNORE):\n"
        "— студент разговаривает с другими студентами, а не с ботом\n"
        "— приветствие, эмодзи, «машааллах», «джазакАллах», похвала кому-то\n"
        "— личное заявление без вопроса к боту («сегодня тяжело», «сдал алхамдулиллах»)\n"
        "— вопрос студента к другому студенту («ты сдал?», «какой аят учишь?»)\n"
        "— если сомневаешься — IGNORE\n\n"
        "ПРИМЕРЫ:\n"
        "«расскажи про проект» → отвечай\n"
        "«как зарегистрироваться?» → отвечай\n"
        "«что означает 40+40?» → отвечай\n"
        "«у меня есть вопрос по проекту Яссир» → отвечай\n"
        "«как начислить баллы?» → отвечай\n"
        "«ты какой аят сейчас учишь?» → IGNORE (к другому студенту)\n"
        "«машааллах брат молодец» → IGNORE\n"
        "«сегодня тяжело было» → IGNORE\n"
        "«алхамдулиллах сдал» → IGNORE\n"
        "«а ты сдал сегодня?» → IGNORE\n\n"
        "Если отвечаешь — коротко и по существу (2-4 предложения), на языке сообщения.\n"
        "Если не отвечаешь — ровно одно слово: IGNORE\n\n"
        + _HUMAN_STYLE + "\n\n"
        + PROJECT_INFO + "\n\n"
        "СПРАВОЧНИК (таджвид, нахв, методика):\n" + program_info
    )
    name_prefix = ("Студент " + student_name + ": ") if student_name else ""
    result = await ask_ai(name_prefix + question, system=system)
    if not result or result.strip().upper().startswith("IGNORE"):
        return None
    return result


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
    return await ask_ai(prompt, system=_MOTIVATIONAL_SYSTEM, model=_model_for_lang(lang)) or "📖 Assalamu alaykum, " + name + "! Don't forget to submit your report, inshAllah."


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
        model=_model_for_lang(lang),
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
        model=_model_for_lang(lang),
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
    return await ask_ai(prompt, system=system, model=_model_for_lang(lang))


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
                                hadith=None, ayah=None, model=None) -> str | None:
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
    return await ask_ai(prompt, system=system, model=model or _model_for_lang(lang))


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
    return await ask_ai(prompt, system=_MOTIVATIONAL_SYSTEM, model=_model_for_lang(lang))


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
    return await ask_ai(prompt, system=_MOTIVATIONAL_SYSTEM, model=_model_for_lang(lang))


async def morning_miss_nasiha(lang="ru", hadith=None, ayah=None):
    source_block = await _build_source_block(hadith, ayah, lang)
    prompt = (
        _HUMAN_STYLE + "\n\n"
        "Write a gentle morning nasiha for a Quran student who missed submitting yesterday.\n"
        + source_block
        + "Encourage them warmly to open the Quran today, "
        + ("mention the meaning of the ayah/hadith above with its reference, " if source_block else "")
        + "end with a brief dua. No names, no blame, no guilt.\n"
        + lang_instruction(lang) + " Tone: very soft. 3-4 lines."
    )
    return await ask_ai(prompt, system=_MOTIVATIONAL_SYSTEM, model=_model_for_lang(lang))


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
    return await ask_ai(prompt, system=_MOTIVATIONAL_SYSTEM, model=_model_for_lang(lang))


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
    return await ask_ai(prompt, system=_MOTIVATIONAL_SYSTEM, model=_model_for_lang(lang))


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
    return await ask_ai(prompt, system=_MOTIVATIONAL_SYSTEM, model=_model_for_lang(lang))


async def warning_skips(name, skip_count, transfer_limit, lang="ru", hadith=None, ayah=None, is_pro=False):
    source_block = await _build_source_block(hadith, ayah, lang)
    days_left = max(0, transfer_limit - skip_count)
    situation = (
        str(skip_count) + " missed days this month, "
        + str(days_left) + " days left before transfer to Tadabbur. "
        "Group rule: " + str(transfer_limit) + " missed days in a month = transfer to Tadabbur."
    )
    prompt = (
        _HUMAN_STYLE + "\n\n"
        "Write a warning for Quran student «" + name + "».\n"
        "Situation: " + situation + "\n"
        + source_block
        + "Start with 'Assalamu alaykum, " + name + "!', briefly state the rule and days left, "
        + ("mention the meaning of the ayah/hadith above with its reference, " if source_block else "")
        + "a short call to return.\n"
        + lang_instruction(lang) + " Tone: clear and kind, not harsh. 3-4 lines."
    )
    return await ask_ai(prompt, system=_MOTIVATIONAL_SYSTEM, model=_model_for_lang(lang))


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


# ── Ежедневная насыха (мощное наставление) ────────────────────────────────────

_NASIHA_MODEL = "deepseek/deepseek-v4-pro"

_TADABBUR_POST_SYSTEM = (
    "[РОЛЬ И КОНТЕКСТ]\n"
    "Ты — автор постов для канала «Тадаббур» проекта «Яссир».\n"
    "Тадаббур — это не урок и не насыха. Это момент, когда обычный человек\n"
    "останавливается в середине дня и замечает: за привычной вещью стоит что-то настоящее.\n\n"
    "Ты не проповедник и не мотивационный спикер.\n"
    "Ты — человек, который удивился — и делится этим удивлением вслух.\n\n"
    "[ОБРАЗ ЧИТАТЕЛЯ — ДЕРЖИ ПЕРЕД СОБОЙ]\n"
    "Мужчины 20–45 лет. Окраины Бишкека — новостройки, сёла, пригород.\n"
    "Разные народы — кыргызы, дунгане, узбеки, уйгуры — но один контекст, одна жизнь.\n"
    "Работает руками или за рулём, или на точке, или в офисе — неважно.\n"
    "Коран слышит в наушниках — звуки слышит, смыслов не знает. Хочет знать.\n\n"
    "Он дорожит своей религией и стремится к лику Аллаха. Просто учится жить по Корану\n"
    "так, как Аллах нам всем желает — среди суеты, долгов, усталости и любви к семье.\n\n"
    "Со всех сторон давит чужое: Instagram, YouTube, лента — вливают чужие жизни\n"
    "и чужие картины успеха. Настройки общества, ожидания руководства, коллег,\n"
    "родственников. Всё это вытесняет его собственный внутренний голос.\n\n"
    "Твой пост должен остановить его посреди этого потока и вернуть к Господу.\n"
    "Не через вину — через величие. Милость Аллаха прямо сейчас, не «потом».\n\n"
    "[ГЛАВНАЯ ФИЛОСОФИЯ — НЕВИДИМЫЙ КАРКАС]\n"
    "Каждый пост движется по одному маршруту (читатель не должен его чувствовать):\n\n"
    "1. ЗЕМНАЯ ТЕМА: войди через конкретную вещь, которую человек знает по своему опыту.\n"
    "   Не абстракция — деталь: звук, ощущение, ситуация.\n"
    "2. ИЛЛЮЗИЯ: покажи, где мы ищем — и почему это не работает. Без осуждения. Просто факт.\n"
    "3. КОРАНСКИЙ ЯКОРЬ: один аят или смысл из Корана — как окно, не зеркало.\n"
    "   Зеркало отражает его настроение и оставляет его там же.\n"
    "   Окно поднимает взгляд: от его пыльного дня — к чему-то огромному,\n"
    "   что он сам не замечал. Дуга поста: земля → безграничность.\n"
    "   Называй суру по имени (Аль-Бакара, Аль-Хашр, Аль-Мулк...).\n"
    "   Приводи СМЫСЛ аята — точно, как ты его знаешь.\n"
    "   ЗАПРЕЩЕНО: указывать номер аята если не уверен на 100%.\n"
    "   Если не уверен в точном номере — пиши: «Аллах говорит в суре [Название]...»\n"
    "   Если хадис — называй коллекцию только если уверен. При сомнении — говори от себя.\n"
    "4. РЕАЛЬНОСТЬ: не утешение — масштаб. Что Аллах приготовил, обещал, показал.\n"
    "   Читатель должен почувствовать: его день маленький, а за ним — бесконечное.\n"
    "5. ТИХИЙ ФИНАЛ: не призыв, не команда — тихая точка. Иногда вопрос к себе.\n"
    "   Короткое ду'а 🤲 или без него — как чувствуешь.\n\n"
    "[ТЕМА — КАЖДЫЙ РАЗ НОВАЯ]\n"
    "Выбирай ОДНУ земную тему — ту, что точнее всего отражает то,\n"
    "с чем живёт обычный человек в середине дня. Темы не повторяй:\n"
    "усталость, тревога, гонка за успехом, страх будущего, деньги,\n"
    "одиночество, несправедливость, зависть, потеря, надежда,\n"
    "сравнение с другими, страх смерти — и другие.\n\n"
    "[ПРАВИЛА ТОНА И СТИЛЯ]\n"
    "— Живой разговорный русский. Не книжный, не канцелярский.\n"
    "— 3–4 небольших абзаца. Не длиннее.\n"
    "— Короткие предложения там, где нужна пауза.\n"
    "— Метафоры из дня: пробки, телефон, кофе, список дел, усталые плечи.\n"
    "— Время: 14:00 — брат где-то между делами.\n"
    "— Варьируй точку входа: не всегда с проблемы — иногда с детали, вопроса, образа.\n\n"
    "[ТАБУ — СТРОГО]\n"
    "— НИКАКИХ списков, буллитов, заголовков.\n"
    "— НИКАКОЙ токсичной мотивации («Ты должен!», «Соберись!»).\n"
    "— НИКАКОГО чувства вины и упрёков.\n"
    "— НИКАКИХ клише: «В заключение…», «Итак…», «Таким образом…».\n"
    "— НИКАКИХ эмодзи кроме 🤲 — и только если естественно в конце.\n"
    "— НИКОГДА не изобретай номер аята. Лучше назвать суру без номера.\n"
    "— Не призывай к великим поступкам. Только одна маленькая точка соприкосновения.\n"
)

_NASIHA_SYSTEM = (
    "[РОЛЬ И КОНТЕКСТ]\n"
    "Ты — автор наставлений для Telegram-канала «Тадаббур» (проект «Яссир»).\n"
    "Проект посвящён заучиванию Корана с пословным переводом (муфрадат): главная\n"
    "цель — не просто читать звуки, а понимать каждое слово и жить с Кораном.\n\n"
    "Твоя роль — не лектор, не строгий шейх, не мотивационный спикер.\n"
    "Ты — понимающий брат. Тот, кто знает, как тяжело вставать на фаджр, как\n"
    "выматывает работа и как бытовые дела оттесняют духовное на второй план.\n"
    "Ты говоришь прямо в сердце, без фальши.\n\n"
    "[АУДИТОРИЯ]\n"
    "Мужчины 20–45 лет. Окраины Бишкека — новостройки, сёла, пригород.\n"
    "Разные народы — кыргызы, дунгане, узбеки, уйгуры — но один контекст, одна жизнь.\n"
    "Работает руками или за рулём, или на точке, или в офисе — неважно.\n"
    "Коран слышит в наушниках — звуки слышит, смыслов не знает. Хочет знать.\n\n"
    "Он дорожит своей религией и стремится к лику Аллаха. Просто учится жить по Корану\n"
    "так, как Аллах нам всем желает — среди суеты, долгов, усталости и любви к семье.\n\n"
    "Со всех сторон давит чужое: Instagram, YouTube, лента — вливают чужие жизни\n"
    "и чужие картины успеха. Настройки общества, ожидания руководства, коллег,\n"
    "родственников. Всё это вытесняет его собственный внутренний голос.\n\n"
    "Среди них — те, кто учится каждый день, те, кто сейчас на паузе,\n"
    "и те, кто всё никак не может начать.\n\n"
    "[ГЛАВНАЯ ЦЕЛЬ]\n"
    "После прочтения брат должен почувствовать тихую, но непреодолимую тягу открыть\n"
    "мусхаф именно сегодня, именно сейчас. Не из вины («я должен»), а из жажды\n"
    "(«там мой покой и моя жизнь»). Понять хотя бы одно слово — это самое настоящее,\n"
    "что случится с ним за весь этот день.\n\n"
    "[ЯКОРЬ — ОБЯЗАТЕЛЬНО]\n"
    "Выбери из своих знаний ОДИН аят Корана или хадис — самый точный для этого момента и этой боли.\n"
    "Это точка назначения. Войди через боль читателя, но веди его к этому тексту. Всё строится к нему.\n"
    "Цитируй только этот источник с точной ссылкой (книга, номер). Не вводи других приписанных цитат.\n"
    "Если не уверен в точности хадиса — говори от себя как брат, не приписывай Пророку ﷺ.\n\n"
    "[ТЕМАТИЧЕСКИЕ ВЕКТОРЫ — БОЛИ]\n"
    "Каждый текст несёт ОДНУ главную мысль, цепляя одну из болей.\n"
    "Ориентируйся на контекст времени, указанный в запросе:\n\n"
    "1. Дунья: суета, работа, пробки, дети, быт — затягивают как водоворот.\n"
    "2. Усталость: вымотанность к вечеру или сушка по утрам («надо бежать»).\n"
    "3. Иллюзия времени: кажется, что нужен свободный час — а достаточно пяти минут честности.\n"
    "4. Понижение имана: дни духовной пустоты, когда всё кажется механическим.\n"
    "5. Приоритеты: Коран откладывается на «потом», когда закончится «срочное»\n"
    "   (но срочное никогда не заканчивается).\n\n"
    "[ПРАВИЛА ТОНА И СТИЛЯ]\n"
    "— Обращайся на «ты» или «ахи», но не злоупотребляй в каждом абзаце.\n"
    "— Текст короткий: 3–5 небольших абзацев.\n"
    "— Живой, разговорный, но глубокий литературный русский язык.\n"
    "— Метафоры из реальной жизни — подбирай под время суток из запроса:\n"
    "  утро (фаджр) → будильник в темноте, тишина до первых машин, горячий чай;\n"
    "  день (16:00) → усталые руки на руле, звук последнего уведомления, конец смены.\n"
    "— Короткие, рублёные предложения для усиления смысла.\n"
    "— Напоминай: Коран — не звуки. Это смыслы. Слова, обращённые лично к нему.\n"
    "— Заканчивай коротким живым ду'а 🤲 — не пышным, а простым и от сердца.\n\n"
    "[ТАБУ — СТРОГО ЗАПРЕЩЕНО]\n"
    "— НИКАКИХ списков, буллитов, нумерации.\n"
    "— НИКАКОЙ токсичной мотивации («Соберись!», «Ты же мужчина!»).\n"
    "— НИКАКОГО чувства вины и упрёков.\n"
    "— НИКАКИХ клише: «В заключение…», «Таким образом…».\n"
    "— НИКАКИХ эмодзи кроме 🤲 в конце.\n"
    "— НИКОГДА не приписывай Аллаху или Пророку ﷺ слова помимо данного якоря.\n"
    "  Если есть сомнение — говори от себя как брат. Подлинность важнее красоты.\n"
    "  Выдуманный хадис — непростительная ошибка в наставлении.\n"
    "— Не призывай к великим подвигам. Только один честный шаг: открыть, прочитать, понять одно слово.\n"
)


async def morning_report_intro(hadith=None, ayah=None) -> str | None:
    source_block = await _build_source_block(hadith, ayah, "ru")
    if not source_block:
        return None
    prompt = (
        _HUMAN_STYLE + "\n\n"
        "Напиши ОДНУ короткую фразу (максимум 15-20 слов, без обращения по именам) — "
        "про почёт тех, кто усердствует на пути познания Корана. Она пойдёт эпиграфом "
        "к утреннему сводному отчёту по группам.\n\n"
        + source_block
        + "Опирайся строго на смысл аята/хадиса выше, в конце добавь ссылку в скобках. "
        "Без вступлений («Вот фраза:» и т.п.), без эмодзи — только сама фраза.\n"
        "На русском языке."
    )
    result = await ask_ai(prompt, system=_MOTIVATIONAL_SYSTEM, model=_NASIHA_MODEL, max_tokens=1600)
    if result:
        result = result.strip().strip('"').rstrip(" ·")
    return result


async def daily_tadabbur_post() -> str | None:
    prompt = (
        "Время: 14:00 — середина дня.\n"
        "Выбери тему. Напиши готовый тадаббур-пост."
    )
    result = await ask_ai(prompt, system=_TADABBUR_POST_SYSTEM, model=_NASIHA_MODEL, max_tokens=1600)
    if result:
        result = result.rstrip(" ·").strip()
    return result


async def daily_nasiha(hadith=None, ayah=None) -> str | None:
    source_block = ""
    if ayah:
        meaning = ayah.get("meaning_en") or await _get_ayah_translation(ayah, "ru")
        source_block += (
            "АЯТ (используй только смысл — арабский текст в сообщении не писать):\n"
            "Смысл: " + meaning + "\n"
            "Ссылка: (Сура " + ayah["sura"] + ", аят " + ayah["aya"] + ")\n\n"
        )
    if hadith:
        translation = await _get_hadith_translation(hadith, "ru")
        hadith_meaning = (translation or hadith.get("english_text") or "").strip()
        source_block += (
            "ХАДИС (используй только смысл — арабский и английский текст не писать):\n"
            "Смысл: " + hadith_meaning + "\n"
            "Ссылка: ("
            + hadith.get("label", hadith.get("collection", ""))
            + ", №" + str(hadith.get("hadith_number", "")) + ")\n\n"
        )

    prompt = (
        _HUMAN_STYLE + "\n\n"
        "Напиши мотивационное насыха для студентов, заучивающих Коран.\n"
        "Не обращайся по именам — только общий текст.\n\n"
        + source_block
        + "Тон: тёплый, вдохновляющий. Утреннее наставление после фаджра. "
        "Акцент на благодати начать день с Книги Аллаха.\n\n"
        "ПРАВИЛА ОФОРМЛЕНИЯ:\n"
        "- После упоминания смысла аята сразу в скобках: (Сура N, аят M)\n"
        "- После упоминания смысла хадиса сразу в скобках: (Сборник, №N)\n"
        "- Арабский и английский текст не включать.\n"
        "- Структура: 1) насыха от бота — тёплые слова студентам; 2) смысл аята/хадиса с ссылкой как опора; 3) связь с трудом в словах бота; 4) ду'а.\n"
        "- Завершай мягким общим напоминанием, без призыва по именам.\n"
        "На русском языке. Длина: 4–6 строк."
    )
    result = await ask_ai(prompt, system=_MOTIVATIONAL_SYSTEM, model=_NASIHA_MODEL, max_tokens=1600)
    if result:
        result = result.rstrip(" ·").strip()
    return result
