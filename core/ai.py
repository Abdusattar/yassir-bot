import asyncio
import random
import logging
import aiohttp
from datetime import datetime
import pytz

from config import OR_API_KEY, OR_URL, AI_MODEL, TZ, PROFILE
from core.i18n import lang_instruction
from core.db import get_yassir_knowledge, get_student_memory, save_chat

log = logging.getLogger(__name__)

_IS_FEMALE = PROFILE == "female"


def _g(m: str, f: str) -> str:
    """Выбирает мужскую или женскую форму в зависимости от профиля бота."""
    return f if _IS_FEMALE else m


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
                    return result["choices"][0]["message"]["content"]
        except Exception as e:
            log.error("OR error (attempt %d): %s", attempt + 1, e)
            if attempt < retries - 1:
                await asyncio.sleep(3)
    return None


async def ask_ai(prompt, system="", retries=3):
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return await _or_call(messages, retries=retries)


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

def _variety_hint():
    topics = [
        "терпение (сабр)", "искренность (ихляс)", "награда за Коран",
        "польза знания", "богобоязненность (таква)", "постоянство в делах",
        "любовь Аллаха к ищущим знание", "достоинство хафиза Корана",
        "важность времени", "благодарность (шукр)", "усердие в поклонении",
        "высокое положение учёных", "Коран как заступник в Судный день",
        "лёгкость после трудности", "дуа за приобретающего знание"
    ]
    today = datetime.now(pytz.timezone(TZ)).strftime("%Y-%m-%d")
    topic = random.choice(topics)
    return ("Сегодня: " + today + ". Возьми НОВЫЙ аят или хадис на тему «" + topic +
            "» — не повторяй те что использовал раньше. Каждый раз разные аяты и хадисы.")


async def check_report(name, tasks_done, lang="ru"):
    all_done = len(tasks_done) >= 3
    prompt = (
        "Ты помощник учителя Корана. Студент *" + name + "* сдал отчёт!\n"
        "Выполненные задания: " + ", ".join(tasks_done) + "\n"
        "Все задания выполнены: " + ("ДА!" if all_done else "нет, частично") + "\n\n"
        "ВАЖНО: НЕ придумывай детали которых нет в отчёте! "
        "Если написано '40+40' — это значит 40 раз новое + 40 раз старое, "
        "НЕ говори 'выучил 80 аятов'. Просто похвали за выполнение заучивания.\n\n"
        + _variety_hint() + "\n\n"
        "СТРУКТУРА (КРАТКО, без воды):\n"
        "1. «БаракАллаху фик, " + name + "!»\n"
        "2. Короткая похвала за задания\n"
        "3. Один краткий аят ИЛИ хадис (с источником)\n"
        + ("4. Кратко: выполнил всё!\n" if all_done else "4. Кратко подбодри закончить\n") +
        lang_instruction(lang) + " ВАЖНО: всего 3-4 коротких строки, без длинных фраз."
    )
    return await ask_ai(prompt)


async def answer_question(question, program_info, group_title, phone=None, group_id=None, student_name=""):
    knowledge = get_yassir_knowledge()
    system = (
        "Ты ассистент учителя Корана по имени Ясир. "
        "Отвечай ТОЛЬКО на основании Корана, хадисов, слов учёных и сподвижников.\n\n"
        "СТИЛЬ ОТВЕТА — ОЧЕНЬ ВАЖНО:\n"
        "- Отвечай КРАТКО и ПО ДЕЛУ, без воды и лишних слов\n"
        "- Но охватывай ВСЕ важные пункты вопроса — ничего не упускай\n"
        "- Пиши ясно, логично, простым языком понятным студенту\n"
        "- Без длинных вступлений и повторов\n"
        "- Если уместно — приводи аят/хадис кратко, с источником\n"
        "- Если студент написал перевод, таджвид или грамматику — ПРОВЕРЬ и укажи ошибки кратко. "
        "Если всё верно — ответь просто '✅ Верно!'\n\n"
        "ЯЗЫК ОТВЕТА: отвечай на том же языке на котором задан вопрос.\n\n"
        "Наша программа:\n" + program_info
    )
    if knowledge:
        system += "\n\nЗнания от учителя:\n" + knowledge

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
        "🤖 Ясир: Ассаляму алейкум! Не могу ответить прямо сейчас 🙏\n"
        "Задай вопрос через несколько минут, или Устаз ответит лично. БаракАллаху фийк! 🕌"
    )


# ── Планировщик / мотивация ───────────────────────────────────────────────────

async def reminder(name, missed_tasks, day, lang="ru"):
    tasks_str = ", ".join(missed_tasks)
    if day == 1:
        urgency, tone = "вчера не успел сдать", "мягко напомни"
    elif day <= 3:
        urgency, tone = str(day) + " дня подряд не сдаёт", "с заботой о важности регулярности"
    elif day <= 7:
        urgency, tone = str(day) + " дней подряд не сдаёт", "настойчиво о потере хифза"
    else:
        urgency, tone = str(day) + " дней подряд не сдаёт", "как " + _g("старший брат", "старшая сестра") + " об ответственности перед Аллахом"
    prompt = (
        "Напиши напоминание для " + _g("студента", "студентки") + " «" + name + "».\n"
        "Ситуация: " + urgency + ". Не сданные: " + tasks_str + ".\n"
        "Тон: " + tone + ".\n"
        "1. Начни с «Ассаляму алейкум, " + name + "!»\n"
        "2. Один аят о важности знания (с сурой и номером)\n"
        "3. Один хадис о заучивании (с источником)\n"
        "4. Слова учёного или сподвижницы\n"
        "5. Дуа за " + _g("студента", "студентку") + "\n"
        + lang_instruction(lang) + " Объём: 8-10 строк."
    )
    return await ask_ai(prompt) or "📖 Ассаляму алейкум, " + name + "! Не забудь сдать уроки, ИншаАллах."


async def group_motivation(missing_names, group_title, lang="ru"):
    names_str = ", ".join(missing_names)
    prompt = (
        "Напиши мотивационное напоминание для группы «" + group_title + "».\n"
        "Не сдали: " + names_str + "\n"
        "1. Перечисли имена\n"
        "2. Аят о важности времени\n"
        "3. Хадис о регулярности\n"
        "4. Слова учёного\n"
        "5. Призыв сдать до конца дня\n"
        + lang_instruction(lang) + " Объём: 8-10 строк."
    )
    return await ask_ai(prompt)


async def personal_streak_praise(name, streak_days, lang="ru"):
    prompt = (
        "Напиши поздравление " + _g("студенту", "студентке") + " «" + name + "».\n"
        "Достижение: " + str(streak_days) + " дней подряд без пропуска!\n"
        "1. «Ассаляму алейкум, " + name + "! МашаАллах!»\n"
        "2. Поздравь с достижением\n"
        "3. Аят о терпении и постоянстве\n"
        "4. Хадис о постоянстве\n"
        "5. Личное дуа\n"
        + lang_instruction(lang) + " Объём: 8-10 строк."
    )
    return await ask_ai(prompt)


async def praise_completed(name, lang="ru"):
    prompt = (
        "Напиши тёплую похвалу " + _g("студенту", "студентке") + " Корана «" + name + "», " + _g("который", "которая") + " СЕГОДНЯ выполнил" + _g("", "а") + " все задания.\n"
        + _variety_hint() + "\n"
        "1. Начни с «БаракАллаху фик, " + name + "!»\n"
        "2. Похвали за усердие сегодня\n"
        "3. Приведи ОДИН аят из Корана (с сурой и номером)\n"
        "4. Приведи ОДИН хадис (с источником: Бухари/Муслим/Тирмизи)\n"
        "5. Приведи слова ОДНОГО учёного или сподвижника\n"
        "6. Краткое дуа\n"
        + lang_instruction(lang) + " Тон: радостный, искренний. Объём: 6-8 строк."
    )
    return await ask_ai(prompt)


async def absent_motivation(name, days, lang="ru"):
    prompt = (
        _g("Студент", "Студентка") + " Корана «" + name + "» уже " + str(days) + " дня не сдавал" + _g("", "а") + " отчёт.\n"
        + _variety_hint() + "\n"
        "Напиши МЯГКОЕ, тёплое напоминание (НЕ ругай!):\n"
        "1. Обратись по имени с теплотой\n"
        "2. Скажи что его не хватает, зови вернуться\n"
        "3. ОДИН аят ИЛИ хадис о постоянстве/возвращении к благому (с источником)\n"
        "4. Краткое дуа и подбадривание\n"
        + lang_instruction(lang) + " Тон: добрый, заботливый, без упрёка. 3-4 строки."
    )
    return await ask_ai(prompt)


async def winner_praise(name, period_label, points, lang="ru"):
    prompt = (
        "Напиши поздравление " + _g("студенту", "студентке") + " Корана «" + name + "» — " + _g("он ЛУЧШИЙ", "она ЛУЧШАЯ") + " за " + period_label +
        " с " + str(points) + " очками!\n"
        + _variety_hint() + "\n"
        "1. Начни с «🏆 МашаАллах, " + name + "!»\n"
        "2. Поздравь с первым местом за " + period_label + "\n"
        "3. Приведи ОДИН аят ИЛИ хадис (с источником) на тему усердия/награды\n"
        "4. Краткое дуа и пожелание продолжать\n"
        + lang_instruction(lang) + " Кратко, тепло: 3-4 строки."
    )
    return await ask_ai(prompt)


async def group_praise(names, lang="ru"):
    names_str = ", ".join(names)
    prompt = (
        "Напиши торжественную похвалу В ГРУППУ для студентов Корана которые СЕГОДНЯ выполнили задания: " + names_str + "\n"
        "1. Начни с «МашаАллах! Табаракаллах!»\n"
        "2. Перечисли имена и похвали\n"
        "3. ОДИН аят из Корана о награде за усердие (с сурой)\n"
        "4. ОДИН хадис о достоинстве изучающих Коран (с источником)\n"
        "5. Слова учёного или сподвижника\n"
        "6. Дуа за всех\n"
        + lang_instruction(lang) + " Тон: вдохновляющий. Объём: 8-10 строк."
    )
    return await ask_ai(prompt)


async def warning_skips(name, skip_count, lang="ru"):
    prompt = (
        "Напиши СЕРЬЁЗНОЕ предупреждение " + _g("студенту", "студентке") + " «" + name + "».\n"
        "Ситуация: " + str(skip_count) + " дней пропусков в этом месяце. При 14 — перевод в группу Тадаббур!\n"
        "1. «Ассаляму алейкум, " + name + "!»\n"
        "2. Предупреди — осталось " + str(14 - skip_count) + " дней до перевода\n"
        "3. Один строгий аят о потере знания\n"
        "4. Хадис о важности постоянства в учёбе\n"
        "5. Призыв вернуться немедленно\n"
        + lang_instruction(lang) + " Тон: серьёзный, но без грубости. 6-8 строк."
    )
    return await ask_ai(prompt)


async def ask_admin_improvement(groups):
    group_titles = ", ".join(g["title"] for g in groups) if groups else "нет групп"
    prompt = (
        "Ты ИИ-ассистент Ясир.\n"
        "Группы: " + group_titles + "\n"
        "Задай Устазу ОДИН вопрос чтобы лучше помогать студентам.\n"
        "Начни с «Устаз, хочу стать лучше...»\n"
        "Язык: русский. Объём: 3-4 строки."
    )
    return await ask_ai(prompt)


async def mystats_comment(name, streak, rank, total_score, days_done, lang="ru"):
    prompt = (
        "Напиши краткий мотивационный комментарий для студента «" + name + "».\n"
        "Его статистика: серия " + str(streak) + " дней подряд, место в рейтинге #" + str(rank) +
        ", всего " + str(total_score) + " баллов за " + str(days_done) + " дней.\n"
        "1 предложение поддержки + 1 дуа.\n"
        + lang_instruction(lang) + " Объём: 2-3 строки."
    )
    return await ask_ai(prompt)
