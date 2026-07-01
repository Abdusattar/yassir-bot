import asyncio
import logging

from config import SUPER_ADMIN_IDS
from core.content import (
    TASK_KEYS, DEFAULT_TASKS, SHORT_TASKS, EXCUSE_WORDS, PROGRAM_INFO, PROG_SECTIONS
)
from core.i18n import T, get_group_lang, LANG_NAMES, task_name, help_student, help_admin
from core.tg import send_message
import core.ai as ai
from core.db import (
    get_group, save_group, get_group_tasks, update_group_tasks, update_group_lang,
    update_group_type, update_group_fallback, update_group_summary, set_group_invite_link,
    get_all_groups, get_students, find_by_phone, find_by_name, add_student,
    register_student, deactivate_student, rename_student, remove_all_students, get_learning_group,
    add_group_admin, remove_group_admin, get_group_admins, is_any_group_admin,
    is_pending_name, set_pending_name, get_pending_text, clear_pending_name,
    get_today_report, save_report, check_text, count_checkmarks, is_checkmarks_only,
    get_streak_days, get_skip_count_month, add_bonus,
    has_attendance_this_week,
    get_knowledge, add_knowledge, delete_knowledge, get_yassir_knowledge, lookup_username,
    find_unlinked_by_name, lookup_by_name_in_chat, find_user_by_phone,
    format_daily_report, format_period_report, get_period_winner,
    get_missing_students, get_date, db
)

log = logging.getLogger(__name__)

_TASK_NAMES = {
    "m": "Заучивание (или 40+40)",
    "r": "Повторение",
    "t": "Слова (или Перевод)",
    "j": "Таджвид",
    "n": "Грамматика (или Нахв)",
    "h": "Хадис",
}

_SECTION_GRP_ADMIN = (
    "👤 КОМАНДЫ УСТАЗА (пиши в группе)\n"
    "/remove Имя — убрать студента (или реплаем)\n"
    "/rename Имя | Новое имя — переименовать\n"
    "/students — список студентов\n\n"
    "/report — отчёт за сегодня\n"
    "/week — за 7 дней\n"
    "/month — за 30 дней\n"
    "/year — за год\n"
    "/rating — рейтинг\n\n"
    "/bonus Имя 5 причина — начислить баллы\n"
    "/groupinfo — настройки группы\n"
    "/settasks m,r,t,j,n,h — задания\n"
    "  m-заучивание r-повторение t-слова\n"
    "  j-таджвид n-грамматика h-хадис\n"
    "/setlang ru — язык (ru/ky/uz/kk/ar)\n"
    "/settype pro/relaxed/tadabbur — тип группы\n"
    "/setfallback -chatid — группа для неактивных\n"
    "/setsummary -chatid — куда слать сводки"
)

_SECTION_SUPER = (
    "🔧 КОМАНДЫ ГЛАВНОГО АДМИНА\n"
    "/setgroup — зарегистрировать группу\n"
    "/admin — (реплаем) назначить устаза группы\n"
    "/unadmin — (реплаем) убрать устаза\n"
    "/admins — список устазов\n"
    "/removeall — удалить всех студентов\n\n"
    "/remind — напомнить несдавшим прямо сейчас\n\n"
    "/teach текст — обучить бота\n"
    "/knowledge — что знает бот\n"
    "/forget N — удалить знание N\n\n"
    "/отчёт Имя — засчитать отчёт вручную"
)


def _section_student(group_tasks, gtype, lang="ru"):
    return help_student(group_tasks, gtype, lang)


def extract_phone(sender):
    if sender is None:
        return ""
    s = str(sender)
    return s.split("@")[0] if "@" in s else s


def is_group_chat(chat_id):
    try:
        return int(str(chat_id)) < 0
    except (ValueError, TypeError):
        return False


def is_admin(phone):
    return phone in SUPER_ADMIN_IDS


def is_group_admin(phone, group_id):
    if phone in SUPER_ADMIN_IDS:
        return True
    return phone in get_group_admins(group_id)


def detect_yassir(text):
    t = text.strip()
    low = t.lower()
    _NAMES = ["ясир", "ясыр", "yassir", "yasir", "yassır", "яссир"]
    # Текст начинается с имени → вернуть часть после имени
    for v in _NAMES:
        if low.startswith(v):
            return t[len(v):].lstrip(" ,!:-—?")
    # Имя упомянуто в середине/конце → весь текст как вопрос
    for v in _NAMES:
        if v in low:
            return t
    return None


def _parse_minus_cmd(text):
    """Parse '- Имя код...' / '/minus Имя код...' → (name, [codes]) or (None, None)."""
    t = text.strip()
    low = t.lower()
    if t.startswith("- ") and len(t) > 2:
        rest = t[2:].strip()
    elif low.startswith("/minus "):
        rest = t[7:].strip()
    elif low.startswith("minus "):
        rest = t[6:].strip()
    else:
        return None, None
    parts = rest.split()
    if not parts:
        return "", []
    codes = []
    while parts and parts[-1].lower() in TASK_KEYS:
        codes.insert(0, parts.pop().lower())
    return " ".join(parts), codes


def _with_knowledge(base: str) -> str:
    extra = get_knowledge()
    if not extra:
        return base
    lines = [base, "\nДОПОЛНИТЕЛЬНЫЕ ПРАВИЛА ОТ УСТАЗА:"]
    for row in extra:
        lines.append("- " + row["text"])
    return "\n".join(lines)


def get_full_program_info():
    return _with_knowledge(PROGRAM_INFO)


# Ключевые слова для определения темы вопроса (НЕ для отчётов — отдельный словарь)
_Q_KEYWORDS = {
    "j": ["таджвид", "tajweed", "махрадж", "makraj", "مخرج", "мадд", "madd", "مد",
          "нун сакина", "نون", "танвин", "idgham", "идгам", "ихфа", "ikhfa", "iqlab",
          "гунна", "gunna", "غنة", "изхар", "izhaar", "калькала", "قلقلة",
          "ташдид", "tashdid", "سكون", "сукун", "сифат", "sifat", "صفة",
          "буква", "звук", "харф"],
    "n":  ["нахв", "nahw", "грамматик", "grammar", "и'раб", "irab", "мубтада", "хабар",
           "мرفوع", "منصوب", "مجرور", "فعل", "فاعل", "فاعل", "مبتدأ", "خبر",
           "падеж", "глагол", "подлежащ", "сказуем", "мафуль", "насб", "джарр", "рафа"],
    "t":  ["муфрадат", "mufradat", "كلمات", "слово", "слова", "словарь",
           "значени", "перевод", "перевести", "переведи", "хамза", "hamza", "همزة"],
}


def _build_reference_for_question(text: str) -> str:
    """Для ответа на вопрос: определяет тему и берёт нужную секцию.
    При неуверенности — возвращает весь PROGRAM_INFO (безопаснее, чем пропустить секцию)."""
    t = text.lower()
    matched = {key for key, kws in _Q_KEYWORDS.items() if any(kw in t for kw in kws)}
    if len(matched) == 1:
        return _with_knowledge(PROG_SECTIONS[matched.pop()])
    return _with_knowledge(PROGRAM_INFO)


def _has_arabic(text):
    return any("؀" <= ch <= "ۿ" for ch in text)


def _build_reference(checks):
    """Собирает только нужные секции справочника по списку проверок."""
    seen = set()
    parts = []
    for check in checks:
        c = check.lower()
        key = None
        if "tajweed" in c:
            key = "j"
        elif "nahw" in c or "grammar" in c:
            key = "n"
        elif "mufradat" in c or "hadith" in c or "writing" in c:
            key = "t"
        if key and key not in seen:
            seen.add(key)
            parts.append(PROG_SECTIONS[key])
    extra = get_knowledge()
    if extra:
        parts.append("\nДОПОЛНИТЕЛЬНЫЕ ПРАВИЛА ОТ УСТАЗА:")
        for row in extra:
            parts.append("- " + row["text"])
    return "\n".join(parts)


async def _verify_and_reply(chat_id, text, group_title, phone, group_id, name, checks, glang="ru", message_id=None):
    try:
        system = (
            "Ты учитель Корана Ясир. Проверь ТОЛЬКО " + ", ".join(checks) + " в сообщении студента.\n\n"
            "🚨 ГЛАВНОЕ ПРАВИЛО ПРОВЕРКИ:\n"
            "Прежде чем заявить об ошибке — НАЙДИ это правило в СПРАВОЧНИКЕ ниже и сверься БУКВА В БУКВУ.\n"
            "Если ответ студента СОВПАДАЕТ со справочником — это ВЕРНО, НЕ исправляй.\n"
            "Если правила нет в справочнике и ты не уверен на 100% — НЕ делай замечание, засчитай как верное.\n"
            "Это касается ВСЕХ предметов: таджвид, нахв (грамматика), муфрадат (перевод).\n\n"
            "📖 ТАДЖВИД: проверяй ТОЛЬКО махрадж (место выхода буквы) и сифат (свойство). "
            "Например: «буква خ — конец горла» правильно или нет. "
            "Сверяйся со справочником СТРОГО буква в букву.\n"
            "⚠️ КРИТИЧЕСКИ ВАЖНО — не путай эти буквы:\n"
            "  ح (ха) → СЕРЕДИНА горла (васат аль-халк)\n"
            "  خ (ха-кх) → КОНЕЦ горла (адна аль-халк)\n"
            "  Это РАЗНЫЕ буквы с РАЗНЫМИ махариджами! ح ≠ خ!\n\n"
            "📝 МУФРАДАТ (это ПЕРЕВОД, слова): студент пишет ОДНО слово из аята + перевод. "
            "Муфрадат = перевод слов = словарный разбор. "
            "Проверяй ДВА момента:\n"
            "1. НАПИСАНИЕ БУКВ арабского слова — все буквы на месте, "
            "правильная хамза (ئ ؤ أ إ ء), та-марбута (ة vs ت), алиф-максура (ى vs ي). "
            "ОГЛАСОВКИ (харакат) НЕ ТРЕБУЙ — студент может писать без них. "
            "НЕ ругай за отсутствие огласовок! "
            "ЗАПРЕЩЕНО делать замечание только из-за отсутствия огласовок — это НЕ ошибка в муфрадат!\n"
            "ПРОВЕРЯЙ ТОЛЬКО БУКВЫ (хуруф) — НЕ проверяй шадду, сукун, танвин, фатху, дамму, кясру, мадду. "
            "Только состав согласных букв должен совпадать. Огласовки и знаки ПОЛНОСТЬЮ ИГНОРИРУЙ!\n"
            "2. ТОЧНОСТЬ ПЕРЕВОДА — соответствует ли перевод значению этого слова в Коране. "
            "Арабские слова часто имеют несколько значений — принимай близкие переводы.\n"
            "Если буквы верны И перевод верен → ВЕРНО\n"
            "Если ошибка в буквах → укажи какая буква неправильная\n"
            "Если перевод неточный → укажи правильное значение\n\n"
            "📚 НАХВ (это ГРАММАТИКА): проверяй ТОЛЬКО ИЪРАБ (конечную огласовку) — "
            "مرفوع (рафъ/дамма) / منصوب (насб/фатха) / مجرور (джарр/кясра) / مجزوم (джазм) "
            "и название члена предложения (فاعل، مفعول به، مبتدأ، خبر и т.д.).\n"
            "ГЛАВНОЕ: проверяй ТОЛЬКО последнюю букву (иъраб). Внутренние огласовки, шадду, сукун ВНУТРИ слова ИГНОРИРУЙ!\n"
            "- Если студент назвал فاعل → конец должен быть مرفوع (дамма)\n"
            "- Если назвал مفعول به → конец منصوب (фатха)\n"
            "- Если назвал مضاف إليه → конец مجرور (кясра)\n"
            "- Если студент НЕ указал роль слова → иъраб НЕ требуй вообще\n"
            "- Если написал слово БЕЗ огласовок → НЕ придирайся, проверь только разбор по смыслу\n"
            "НЕ ПУТАЙ фатху (َ) и кясру (ِ) на конце — это грубая ошибка!\n"
            "ТАБЛИЦА СООТВЕТСТВИЙ (роль → иъраб):\n"
            "- فاعل (подлежащее) → رفع (марфуъ)\n"
            "- نائب الفاعل (замена подлежащего) → رفع\n"
            "- مبتدأ (подлежащее именное) → رفع\n"
            "- خبر (сказуемое) → رفع\n"
            "- مفعول به (прямое дополнение) → نصب (мансуб)\n"
            "- مفعول مطلق / مفعول لأجله / حال / تمييز → نصب\n"
            "- اسم إنَّ → نصب, خبر إنَّ → رفع\n"
            "- اسم كان → رفع, خبر كان → نصب\n"
            "- مضاف إليه (то что после идафы) → جر (маджрур)\n"
            "- اسم مجرور (после харфа джарр) → جر\n"
            "- الفعل المضارع после ناصب → نصب, после جازم → جزم\n"
            "Если студент написал роль и иъраб, которые НЕ совпадают с таблицей → это ОШИБКА, укажи правильный.\n\n"
            "⚠️ ВАЖНО ДЛЯ НАХВ — ХАРФЫ И ДАМИРЫ:\n"
            "Эти слова НЕ являются исмом — они харф или дамир:\n"
            "ХАРФЫ НАСБ — ставят следующий исм в насб: إنَّ / أنَّ / لكنَّ / كأنَّ / ليتَ / لعلَّ\n"
            "  → أنَّكم = أنَّ (харф насб) + كم (дамир муттасиль) — НЕ исм!\n"
            "ДАМИРЫ МУТТАСИЛЯ — НЕ исм: كَ / كم / هُ / هم / نا / ي / ك\n"
            "ДАМИРЫ МУНФАСИЛЯ — это ДАМИР, не просто исм: أنا / أنتَ / أنتم / هو / هي / هم / نحن\n"
            "НЕ называй дамир или харф словом «существительное» — это грубая ошибка!\n\n"
            "⚠️ НЕ смешивай предметы! Если проверяешь муфрадат — не требуй огласовок. "
            "Если проверяешь нахв — требуй правильный иъраб.\n\n"
            "ПРАВИЛА ОТВЕТА (СТРОГО!):\n"
            "- Если всё ВЕРНО → ответь ровно одним словом: ВЕРНО\n"
            "- ЗАПРЕЩЕНО перечислять каждое слово отдельно — если всё верно, пиши только ВЕРНО\n"
            "- Если есть ОШИБКА → МАКСИМУМ 3 строки: 1) что неверно 2) как правильно\n"
            "- ЗАПРЕЩЕНО: длинные объяснения, нумерованные списки, похвала за каждое слово\n\n"
            "СПРАВОЧНИК (сверяйся с ним):\n" + _build_reference(checks)
        )
        prompt = "Сообщение студента " + name + ":\n" + text
        result = await ai.ask_ai(prompt, system=system, model="google/gemini-2.5-flash")
        if result:
            import re as _re
            result = _re.sub(r"```[a-z]*\n?", "", result).strip().rstrip("`").strip()
            if result.startswith("[") or result.startswith("{"):
                result = None
        if result and "ВЕРНО" in result.upper()[:20]:
            await send_message(chat_id, "✅", reply_to_message_id=message_id)
        elif result:
            await send_message(chat_id, "🤖 Ясир:\n" + result, reply_to_message_id=message_id)
    except Exception as e:
        log.error("verify error: %s", e)


async def process_message(chat_id, sender, text, sender_name="", is_media=False, reply_to_id=None, message_id=None, reply_to_text=""):
    phone = extract_phone(sender)
    text = (text or "").strip()
    # Telegram в группах добавляет @botname к командам: /help@yassirquranbot → /help
    # Только для команд студентов — админские команды работают только при ручном вводе
    _STUDENT_CMDS = {"/help", "/mystats", "/rating", "/id"}
    if text.startswith("/"):
        at = text.find("@")
        if at != -1 and " " not in text[:at]:
            cmd = text[:at]
            if cmd in _STUDENT_CMDS:
                text = cmd + text[text.find(" ", at) if " " in text[at:] else len(text):]
    if not text and not is_media:
        return

    # /id — узнать свой id
    if text == "/id":
        await send_message(chat_id,
            "🆔 Твой user_id: " + str(phone) + "\n"
            "💬 id этого чата: " + str(chat_id) + "\n\n"
            "Чтобы стать админом — впиши свой user_id в ADMIN_IDS.")
        return

    is_group = is_group_chat(chat_id)

    # ── Личные команды Устаза (личка) ─────────────────────────────────────────
    if is_admin(phone):
        if text.startswith("/отчёт ") or text.startswith("/отчет "):
            name_part = text.split(None, 1)[1].strip() if len(text.split(None, 1)) > 1 else ""
            if not name_part:
                await send_message(chat_id, "Формат: /отчёт Имя")
                return
            matched = None
            for g in get_all_groups():
                for st in get_students(g["id"]):
                    if name_part.lower() in st["name"].lower():
                        matched = (st, g)
                        break
                if matched:
                    break
            if not matched:
                await send_message(chat_id, "❌ Студент не найден: " + name_part)
                return
            st, g = matched
            td = {k: True for k in get_group_tasks(g)}
            save_report(st["id"], g["id"], get_date(), td)
            await send_message(chat_id, "✅ Отчёт засчитан: " + st["name"])
            return

        if text == "/start":
            await send_message(chat_id,
                "👋 Ассаляму алейкум, Устаз! 🕌\n"
                "Я — Ясир, ваш помощник.\n\n"
                "🔧 НАСТРОЙКА ГРУППЫ (внутри группы)\n"
                "/setgroup — подключить группу\n"
                "/settasks m,r,t — задания группы\n"
                "/setlang ru — язык группы\n"
                "/settype pro|relaxed|tadabbur — тип группы\n"
                "/setfallback [chat_id] — куда переводить неактивных\n\n"
                "Типы групп:\n"
                "pro — соревновательная (14 дней без отчёта → Тадаббур)\n"
                "relaxed — расслабленная (30 дней → Тадаббур)\n"
                "tadabbur — красота и смыслы Корана (не учебная, для всех)\n\n"
                "👤 СТУДЕНТЫ\n"
                "/add Имя — добавить\n"
                "/add 996XXX Имя — с номером\n"
                "/remove Имя — удалить (или реплаем)\n"
                "/students — список\n\n"
                "📊 ОТЧЁТЫ\n"
                "/report — сегодня\n"
                "/week — неделя\n"
                "/month — месяц\n\n"
                "🤖 ЯСИР (в личке)\n"
                "/teach правило — научить\n"
                "/knowledge — все знания\n\n"
                "БаракАллаху фийк, Устаз 🤲"
            )
            return

        if text.startswith("/teach "):
            knowledge = text[7:].strip()
            if knowledge:
                add_knowledge(knowledge)
                await send_message(chat_id, "✅ Ясир запомнил! 🧠\n\n" + knowledge)
            return

        if text == "/knowledge":
            rows = get_knowledge()
            if not rows:
                await send_message(chat_id, "Знаний пока нет. Добавь: /teach правило")
            else:
                lines = ["🧠 Знания Ясира:\n"]
                for row in rows:
                    lines.append(str(row["id"]) + ". " + row["text"])
                lines.append("\nУдалить: /forget номер")
                await send_message(chat_id, "\n".join(lines))
            return

        if text.startswith("/forget "):
            num = text[8:].strip()
            if num.isdigit():
                delete_knowledge(int(num))
                await send_message(chat_id, "✅ Удалено из знаний Ясира")
            return

        if text == "/dbstats":
            with db() as c:
                total_users = c.execute("SELECT COUNT(*) FROM users WHERE active=1").fetchone()[0]
                with_phone = c.execute("SELECT COUNT(*) FROM users WHERE active=1 AND phone IS NOT NULL").fetchone()[0]
                no_phone = c.execute("""
                    SELECT u.name, g.title
                    FROM users u
                    JOIN user_groups ug ON u.id=ug.user_id
                    JOIN groups g ON g.id=ug.group_id
                    WHERE u.active=1 AND u.phone IS NULL AND ug.role='student' AND ug.active=1
                    ORDER BY g.id, u.name
                """).fetchall()
                groups = c.execute("""
                    SELECT g.title, g.group_type, COUNT(ug.user_id) as cnt
                    FROM groups g
                    LEFT JOIN user_groups ug ON g.id=ug.group_id AND ug.role='student' AND ug.active=1
                    WHERE g.active=1
                    GROUP BY g.id ORDER BY g.id
                """).fetchall()
                today_reports = c.execute(
                    "SELECT COUNT(DISTINCT student_id) FROM score_events WHERE date=? AND category='task'",
                    (get_date(),)
                ).fetchone()[0]
            lines = ["📊 База данных (сервер)\n"]
            lines.append("👥 Пользователей: " + str(total_users))
            lines.append("  ✅ С Telegram ID: " + str(with_phone))
            lines.append("  ⬜ Без ID: " + str(total_users - with_phone))
            if no_phone:
                for r in no_phone:
                    lines.append("    • " + r["name"] + " — " + (r["title"] or "?"))
            lines.append("\n📋 Группы:")
            for g in groups:
                gtype = g["group_type"] or "relaxed"
                label = " [тадаббур]" if gtype == "tadabbur" else ""
                lines.append("  • " + (g["title"] or "?") + label + " — " + str(g["cnt"]) + " студентов")
            lines.append("\n📈 Отчётов сегодня: " + str(today_reports))
            await send_message(chat_id, "\n".join(lines))
            return

        if text == "/morning_report":
            from core.scheduler import morning_tadabbur_report
            await send_message(chat_id, "⏳ Отправляю итоги вчера в тадаббур...")
            await morning_tadabbur_report()
            await send_message(chat_id, "✅ Готово.")
            return

        if text == "/remind":
            from core.scheduler import personal_reminders
            groups = get_all_groups()
            non_tad = [g for g in groups if (g["group_type"] or "relaxed") != "tadabbur"]
            await send_message(chat_id, "📖 Запускаю напоминания — " + str(len(non_tad)) + " групп...")
            asyncio.create_task(personal_reminders())
            return

    # ── Личка ────────────────────────────────────────────────────────────────
    if not is_group:
        if is_admin(phone):
            if text and not text.startswith("/"):
                answer = await ai.answer_question(
                    text, _build_reference_for_question(text), "личка суперадмина", phone, None, sender_name
                )
                await send_message(chat_id, answer)
            return
        if is_any_group_admin(phone):
            if text and not text.startswith("/"):
                answer = await ai.answer_ustaz_question(
                    text, _build_reference_for_question(text), sender_name
                )
                await send_message(chat_id, answer)
            elif text == "/start":
                await send_message(chat_id,
                    "👋 Ассаляму алейкум, Устаз! 🕌\n"
                    "Пиши мне в личку любой вопрос по таджвиду, нахву или программе — отвечу 🤲"
                )
            return
        await send_message(chat_id,
            "Ассаляму алейкум! 🕌\n"
            "Чтобы зарегистрироваться — напиши любое сообщение в своей учебной группе, "
            "и бот попросит твоё имя 📝"
        )
        return

    group = get_group(chat_id)

    if text == "/setgroup":
        if not is_admin(phone):
            return
        from core.tg import tg_call
        chat_info = await tg_call("getChat", {"chat_id": int(chat_id)})
        title = (chat_info or {}).get("result", {}).get("title", sender_name or chat_id)
        save_group(chat_id, title)
        grp = get_group(chat_id)
        # Авто-назначение устазов: все Telegram-админы группы кроме суперадминов и ботов
        admins_resp = await tg_call("getChatAdministrators", {"chat_id": int(chat_id)})
        auto_admins = []
        for member in (admins_resp or {}).get("result", []):
            u = member.get("user", {})
            if u.get("is_bot"):
                continue
            uid = str(u.get("id", ""))
            if uid in SUPER_ADMIN_IDS:
                continue
            add_group_admin(grp["id"], uid)
            name = (u.get("first_name") or "").strip()
            if u.get("last_name"):
                name = (name + " " + u["last_name"]).strip()
            auto_admins.append(name or uid)
        msg = "✅ Группа зарегистрирована: " + str(title)
        if auto_admins:
            msg += "\n👤 Устазы: " + ", ".join(auto_admins)
        msg += "\nТип: /settype pro|relaxed|tadabbur\nЗадания: /settasks m,r,t,j"
        await send_message(chat_id, msg)
        return

    if not group:
        return

    group_id = group["id"]
    group_tasks = get_group_tasks(group)
    glang = get_group_lang(group)
    gtype = group["group_type"] or "relaxed"

    # Тадаббур — только для админов, обычные сообщения игнорируем
    if gtype == "tadabbur" and not is_group_admin(phone, group_id):
        return

    # ── Регистрация в группе ──────────────────────────────────────────────────
    if not is_group_admin(phone, group_id):
        s_reg = find_by_phone(phone, group_id)
        if not s_reg:
            if text.startswith("/"):
                if is_pending_name(phone, group_id):
                    await send_message(chat_id, T("ask_name", glang))
                else:
                    greeting = ("Ассаляму алейкум, " + sender_name + "! 🌙\n") if sender_name else "Ассаляму алейкум! 🌙\n"
                    set_pending_name(phone, group_id, "")
                    await send_message(chat_id, greeting + T("ask_name", glang))
                return
            if is_pending_name(phone, group_id):
                import re as _re
                raw_input = text.strip()
                # Служебные слова во время ожидания имени — напомнить попросить имя
                _SKIP_WORDS = {"help", "хелп", "помощь", "start", "старт", "hi", "привет", "салам", "salam"}
                if raw_input.lower() in _SKIP_WORDS:
                    await send_message(chat_id, T("ask_name", glang))
                    return
                # Если ещё не сохранён отчёт — проверим, не отчёт ли это сообщение
                if not get_pending_text(phone, group_id):
                    td_pre = check_text(raw_input)
                    if sum(1 for k in group_tasks if td_pre.get(k)) > 0:
                        set_pending_name(phone, group_id, raw_input)
                        await send_message(chat_id, T("ask_name", glang))
                        return
                # Извлекаем имя через ИИ; если не получилось — пробуем Telegram-имя
                new_name = (await ai.extract_name(raw_input) or "").strip() or None
                if not new_name and sender_name:
                    new_name = (await ai.extract_name(sender_name) or "").strip() or None
                if not new_name:
                    await send_message(chat_id, T("ask_name_again", glang))
                    return
                # Проверяем что это действительно имя человека
                if not await ai.is_valid_name(new_name):
                    await send_message(chat_id, T("ask_name_confirm", glang, name=new_name))
                    return
                # Проверяем: не студент ли уже в другой учебной группе
                gtype = group["group_type"] or "relaxed"
                if gtype != "tadabbur":
                    existing_lg = get_learning_group(phone)
                    if existing_lg and existing_lg["id"] != group_id:
                        clear_pending_name(phone, group_id)
                        await send_message(chat_id,
                            new_name + ", ты уже студент группы «" + (existing_lg["title"] or "") + "». "
                            "Студент может быть только в одной учебной группе.")
                        return
                # Привязать к существующему студенту без ID, иначе создать нового
                existing_s = find_unlinked_by_name(new_name, group_id)
                if existing_s:
                    register_student(existing_s["id"], phone)
                    sid = existing_s["id"]
                else:
                    sid = add_student(new_name, group_id, phone)
                # Засчитать сохранённый первый отчёт если был
                saved = get_pending_text(phone, group_id)
                clear_pending_name(phone, group_id)
                await send_message(chat_id, T("registered_group", glang, name=new_name))
                for ap in SUPER_ADMIN_IDS:
                    await send_message(ap, "👤 " + new_name + " зарегистрировался в «" + (group["title"] or str(chat_id)) + "»")
                if saved and saved.strip():
                    td = check_text(saved)
                    sc = sum(1 for k in group_tasks if td.get(k))
                    if sc > 0:
                        save_report(sid, group_id, get_date(), td)
                        done_list = [task_name(k, glang) for k in group_tasks if td.get(k)]
                        await send_message(chat_id, "📖 Засчитан отчёт из первого сообщения:\n" + "\n".join("✅ " + n for n in done_list))
                return
            else:
                # Уже зарегистрирован в другой группе — авторегистрация
                existing_user = find_user_by_phone(phone)
                if existing_user:
                    add_student(existing_user["name"], group_id, phone)
                    await send_message(chat_id, T("registered_group", glang, name=existing_user["name"]))
                    return
                # Первый раз в системе — пробуем авто-матч по Telegram-имени
                # Только если точное совпадение И ровно один такой незарегистрированный
                if sender_name:
                    tg_name = (await ai.extract_name(sender_name) or "").strip() or None
                    if tg_name:
                        gtype_chk = group["group_type"] or "relaxed"
                        if gtype_chk != "tadabbur":
                            existing_lg = get_learning_group(phone)
                            if existing_lg and existing_lg["id"] != group_id:
                                tg_name = None
                        if tg_name:
                            with db() as _c:
                                exact_count = _c.execute(
                                    "SELECT COUNT(*) FROM users u JOIN user_groups ug ON u.id=ug.user_id "
                                    "WHERE LOWER(u.name)=LOWER(?) AND ug.group_id=? AND ug.active=1 AND u.phone IS NULL",
                                    (tg_name, group_id)
                                ).fetchone()[0]
                            if exact_count == 1:
                                existing_s = find_unlinked_by_name(tg_name, group_id)
                                if existing_s:
                                    register_student(existing_s["id"], phone)
                                    sid = existing_s["id"]
                                    greeting = "Ассаляму алейкум, " + tg_name + "! 🌙\n"
                                    await send_message(chat_id, greeting + T("registered_group", glang, name=tg_name))
                                    for ap in SUPER_ADMIN_IDS:
                                        await send_message(ap, "👤 " + tg_name + " авторегистрация в «" + (group["title"] or str(chat_id)) + "»")
                                    return
                # Повторная проверка: chat_member-апдейт мог уже поставить pending до нас
                if is_pending_name(phone, group_id):
                    await send_message(chat_id, T("ask_name", glang))
                    return
                set_pending_name(phone, group_id, text)
                greeting = ("Ассаляму алейкум, " + sender_name + "! 🌙\n") if sender_name else "Ассаляму алейкум! 🌙\n"
                await send_message(chat_id, greeting + T("ask_name", glang))
                return

    # ── Управление группой (только группа-админ) ───────────────────────────────
    if (text.startswith("/admin") or text == "/admin") and phone in SUPER_ADMIN_IDS:
        if not reply_to_id:
            await send_message(chat_id, "Ответь реплаем на сообщение человека и напиши /admin")
            return
        add_group_admin(group_id, str(reply_to_id))
        await send_message(chat_id, "✅ Назначен устазом группы")
        return

    if (text.startswith("/unadmin") or text == "/unadmin") and phone in SUPER_ADMIN_IDS:
        if not reply_to_id:
            await send_message(chat_id, "Ответь реплаем на сообщение человека и напиши /unadmin")
            return
        remove_group_admin(group_id, str(reply_to_id))
        await send_message(chat_id, "✅ Убран из устазов группы")
        return

    if text == "/admins":
        admins = get_group_admins(group_id)
        lines = ["👤 Админы группы:"]
        lines.append("Главные: " + ", ".join(SUPER_ADMIN_IDS))
        if admins:
            lines.append("Группы: " + ", ".join(admins))
        await send_message(chat_id, "\n".join(lines))
        return

    if text.startswith("/settasks ") and is_group_admin(phone, group_id):
        tasks_str = text[10:].strip().lower()
        valid = [k.strip() for k in tasks_str.split(",") if k.strip() in TASK_KEYS]
        if valid:
            update_group_tasks(chat_id, ",".join(valid))
            names = [DEFAULT_TASKS[k] for k in valid]
            await send_message(chat_id, "✅ Задания обновлены:\n" + "\n".join(names))
        else:
            await send_message(chat_id, "Напиши: /settasks m,r,t\nДоступные: m r t j n h")
        return

    if text.startswith("/setlang ") and is_group_admin(phone, group_id):
        lang_code = text[9:].strip().lower()
        if lang_code in LANG_NAMES:
            update_group_lang(chat_id, lang_code)
            await send_message(chat_id,
                "✅ Язык группы: " + LANG_NAMES[lang_code] + "\n"
                "Отчёты и напоминания теперь на этом языке.")
        else:
            codes = "\n".join(c + " — " + n for c, n in LANG_NAMES.items())
            await send_message(chat_id, "Доступные языки:\n" + codes + "\n\nНапример: /setlang ky")
        return

    if text == "/lang":
        cur = get_group_lang(group)
        await send_message(chat_id,
            "🌍 Язык группы: " + LANG_NAMES.get(cur, "русский") + " (" + cur + ")\n\n"
            "Сменить: /setlang код\n" +
            "\n".join(c + " — " + n for c, n in LANG_NAMES.items()))
        return

    # ── Управление типом группы (новые команды) ───────────────────────────────
    if text.startswith("/settype ") and is_group_admin(phone, group_id):
        gtype = text[9:].strip().lower()
        if gtype in ("pro", "relaxed", "tadabbur", "prep"):
            update_group_type(chat_id, gtype)
            type_desc = {
                "pro": "Про-группа (10 дней без отчёта → Тадаббур)",
                "relaxed": "Расслабленная (20 дней подряд → Тадаббур)",
                "tadabbur": "Тадаббур — пространство красоты и смыслов Корана (не учебная группа)",
                "prep": "Подготовительная (14 дней, ≥5 сдал → выбор relaxed-группы)",
            }
            await send_message(chat_id, "✅ Тип группы: " + type_desc[gtype])
        else:
            await send_message(chat_id, "Доступные типы:\n/settype pro\n/settype relaxed\n/settype tadabbur\n/settype prep")
        return

    if text.startswith("/setlink ") and is_group_admin(phone, group_id):
        link = text[9:].strip()
        if link.startswith("https://t.me/"):
            set_group_invite_link(group["id"], link)
            await send_message(chat_id, "✅ Ссылка-приглашение сохранена для этой группы.")
        else:
            await send_message(chat_id, "Напиши: /setlink https://t.me/+xxxx")
        return

    if text.startswith("/setfallback ") and is_group_admin(phone, group_id):
        fallback_id = text[13:].strip()
        if fallback_id.lstrip("-").isdigit():
            update_group_fallback(chat_id, fallback_id)
            await send_message(chat_id,
                "✅ Группа для перевода неактивных: " + fallback_id + "\n"
                "Сюда будут переводиться студенты превысившие порог пропусков.")
        else:
            await send_message(chat_id, "Напиши: /setfallback -1234567890 (id целевой группы)")
        return

    if text.startswith("/setsummary ") and is_group_admin(phone, group_id):
        summary_id = text[12:].strip()
        if summary_id.lstrip("-").isdigit():
            update_group_summary(chat_id, summary_id)
            await send_message(chat_id,
                "✅ Группа для сводок: " + summary_id + "\n"
                "Туда будут отправляться ежедневные отчёты этой pro-группы.")
        else:
            await send_message(chat_id, "Напиши: /setsummary -1234567890")
        return

    if text == "/groupinfo" and is_group_admin(phone, group_id):
        gtype = group["group_type"] or "relaxed"
        lines = [
            "ℹ️ Информация о группе:",
            "Название: " + (group["title"] or chat_id),
            "Тип: " + gtype,
            "Задания: " + ", ".join(DEFAULT_TASKS[k] for k in group_tasks),
            "Язык: " + LANG_NAMES.get(glang, glang),
            "Fallback (для неактивных): " + (group["fallback_chat_id"] or "не задан"),
            "Summary (для сводок): " + (group["summary_chat_id"] or "не задан"),
        ]
        await send_message(chat_id, "\n".join(lines))
        return



    # ── Отмена задания: "- Имя код" / "/minus Имя код" ───────────────────────
    _m_name, _m_codes = _parse_minus_cmd(text)
    if _m_name is not None and is_group_admin(phone, group_id):
        if not _m_name or not _m_codes:
            await send_message(chat_id,
                "❌ Формат: - Имя код\nПример: - Азиз t r\n\n"
                "Коды заданий: m r t j n h")
            return
        st = find_by_name(_m_name, group_id)
        if not st:
            await send_message(chat_id, "❌ Студент «" + _m_name + "» не найден в этой группе")
            return
        today = get_date()
        cancelled, not_found = [], []
        with db() as c:
            for code in _m_codes:
                exists = c.execute(
                    "SELECT 1 FROM score_events"
                    " WHERE student_id=? AND group_id=? AND date=? AND category='task' AND subcategory=?",
                    (st["id"], group_id, today, code)
                ).fetchone()
                if exists:
                    c.execute(
                        "DELETE FROM score_events"
                        " WHERE student_id=? AND group_id=? AND date=? AND category='task' AND subcategory=?",
                        (st["id"], group_id, today, code)
                    )
                    cancelled.append(DEFAULT_TASKS.get(code, code))
                else:
                    not_found.append(DEFAULT_TASKS.get(code, code))
        if cancelled:
            lines = ["❌ По решению устаза аннулировано у " + st["name"] + ":"]
            lines += ["• " + n for n in cancelled]
            lines.append("\nПо вопросам обращайтесь к устазу. 🤲")
            await send_message(chat_id, "\n".join(lines))
        if not_found:
            info = ["ℹ️ Сегодня не найдено у " + st["name"] + ":"]
            info += ["• " + n for n in not_found]
            await send_message(chat_id, "\n".join(info))
        return

    # ── Студенты ──────────────────────────────────────────────────────────────
    if text == "/remove" and reply_to_id and is_group_admin(phone, group_id):
        for s in get_students(group_id):
            if s["phone"] == str(reply_to_id):
                deactivate_student(s["id"], group_id)
                await send_message(chat_id, "✅ " + s["name"] + " удалён!")
                return
        await send_message(chat_id, "Студент не найден в этой группе")
        return

    if text.startswith("/remove ") and is_group_admin(phone, group_id):
        name = text[8:].strip()
        for s in get_students(group_id):
            if s["name"].lower() == name.lower():
                deactivate_student(s["id"], group_id)
                await send_message(chat_id, "✅ " + name + " удалён!")
                return
        await send_message(chat_id, "Студент не найден")
        return

    if text.startswith("/rename ") and is_group_admin(phone, group_id):
        parts = text[8:].strip().split("|")
        if len(parts) != 2:
            await send_message(chat_id, "Формат:\n/rename Имя | Новое имя\n/rename 3 | Новое имя")
            return
        old_part = parts[0].strip()
        new_name = parts[1].strip()
        students = get_students(group_id)
        found = None
        if old_part.isdigit():
            idx = int(old_part) - 1
            if 0 <= idx < len(students):
                found = students[idx]
        else:
            for s in students:
                if s["name"].lower() == old_part.lower():
                    found = s
                    break
        if not found:
            await send_message(chat_id, "Студент не найден. Список: /students")
            return
        old_name = found["name"]
        from core.db import rename_student
        rename_student(found["id"], new_name)
        await send_message(chat_id, "✅ " + old_name + " → " + new_name)
        return

    if text == "/removeall" and is_admin(phone):
        cnt = len(get_students(group_id))
        await send_message(chat_id,
            "⚠️ Удалить ВСЕХ студентов (" + str(cnt) + ")?\n"
            "Напиши: /removeall_да для подтверждения")
        return

    if text == "/removeall_да" and is_admin(phone):
        cnt = len(get_students(group_id))
        remove_all_students(group_id)
        await send_message(chat_id, "✅ Удалены все студенты (" + str(cnt) + ").")
        return

    if text == "/students":
        students = get_students(group_id)
        gtype = group["group_type"] or "relaxed"
        lines = ["📋 Студенты — " + (group["title"] or chat_id) + " [" + gtype + "]:\n"]
        lines.append("Задания: " + " | ".join(DEFAULT_TASKS[k] for k in group_tasks) + "\n")
        for i, s in enumerate(students, 1):
            status = "✅" if s["phone"] else "⬜"
            lines.append(status + " " + str(i) + ". " + s["name"])
        await send_message(chat_id, "\n".join(lines))
        return

    # ── Отчёты ────────────────────────────────────────────────────────────────
    if text == "/report":
        await send_message(chat_id, format_daily_report(group_id, group["title"] or chat_id, group_tasks))
        return

    if text == "/week":
        await send_message(chat_id, format_period_report(group_id, group["title"] or chat_id, group_tasks, 7))
        return

    if text == "/month":
        await send_message(chat_id, format_period_report(group_id, group["title"] or chat_id, group_tasks, 30))
        return

    if text == "/year":
        await send_message(chat_id, format_period_report(group_id, group["title"] or chat_id, group_tasks, 365))
        return

    if text == "/rating":
        import pytz
        from datetime import timedelta
        from config import TZ
        week_ago = (__import__('datetime').datetime.now(pytz.timezone(TZ)).date() - timedelta(days=7)).isoformat()
        with db() as c:
            rows = c.execute("""
                SELECT u.name,
                       COALESCE(SUM(e.points),0) as total,
                       COUNT(DISTINCT CASE WHEN e.category='task' THEN e.date END) as days
                FROM users u
                JOIN user_groups ug ON u.id=ug.user_id
                LEFT JOIN score_events e ON u.id=e.student_id AND e.group_id=? AND e.date>=?
                WHERE ug.group_id=? AND ug.role='student' AND ug.active=1
                GROUP BY u.id ORDER BY total DESC
            """, (group_id, week_ago, group_id)).fetchall()
        medals = ["🥇", "🥈", "🥉"]
        lines = [T("rating_header", glang, title=group["title"] or chat_id)]
        for i, r in enumerate(rows):
            medal = medals[i] if i < 3 else str(i + 1) + "."
            lines.append(medal + " " + r["name"] + " — " + str(r["total"]) + " " + T("rating_points", glang) + " (" + str(r["days"]) + " " + T("rating_days", glang) + ")")
        await send_message(chat_id, "\n".join(lines))
        return

    if text == "/help":
        s_h = find_by_phone(phone, group_id)
        sections = []
        if s_h:
            sections.append(_section_student(group_tasks, group["group_type"] or "relaxed", glang))
        if is_group_admin(phone, group_id):
            sections.append(help_admin(glang))
        if phone in SUPER_ADMIN_IDS:
            sections.append(_SECTION_SUPER)
        if sections:
            await send_message(chat_id, ("\n\n" + "─" * 20 + "\n\n").join(sections))
        return

    if text == "/mystats":
        s_check = find_by_phone(phone, group_id)
        if not s_check:
            await send_message(chat_id, T("not_registered", glang))
            return
        streak = get_streak_days(s_check["id"])
        skips_month = get_skip_count_month(s_check["id"])
        with db() as c:
            total_row = c.execute(
                "SELECT COALESCE(SUM(points),0) as total FROM score_events WHERE student_id=?",
                (s_check["id"],)
            ).fetchone()
            days_row = c.execute(
                "SELECT COUNT(DISTINCT date) as days FROM score_events"
                " WHERE student_id=? AND category='task'",
                (s_check["id"],)
            ).fetchone()
            rank_rows = c.execute("""
                SELECT u.id, COALESCE(SUM(e.points),0) as grand
                FROM users u
                JOIN user_groups ug ON u.id=ug.user_id
                LEFT JOIN score_events e ON e.student_id=u.id AND e.group_id=?
                WHERE ug.group_id=? AND ug.role='student' AND ug.active=1
                GROUP BY u.id ORDER BY grand DESC
            """, (group_id, group_id)).fetchall()
        total_score = total_row["total"] or 0
        days_done = days_row["days"] or 0
        rank = next((i + 1 for i, r in enumerate(rank_rows) if r["id"] == s_check["id"]), "?")
        today_rep = get_today_report(s_check["id"], group_id)
        today_done = sum(1 for k in group_tasks if today_rep and today_rep[k]) if today_rep else 0
        gtype = group["group_type"] or "relaxed"
        limit_days = 14 if gtype == "pro" else 30
        import calendar
        _month_names_ru = ["январе","феврале","марте","апреле","мае","июне",
                           "июле","августе","сентябре","октябре","ноябре","декабре"]
        from datetime import datetime as _dt
        _cur_month = _dt.now().month
        month_label = _month_names_ru[_cur_month - 1]

        lines = [
            T("mystats_title", glang, name=s_check["name"]),
            T("mystats_streak", glang, n=streak),
            T("mystats_rank", glang, n=rank),
            T("mystats_points", glang, n=total_score),
            T("mystats_days", glang, n=days_done),
            T("mystats_skips", glang, n=skips_month, limit=limit_days, month=month_label),
            T("mystats_today", glang, done=today_done, total=len(group_tasks)),
        ]
        await send_message(chat_id, "\n".join(lines))
        comment = await ai.mystats_comment(s_check["name"], streak, rank, total_score, days_done, glang)
        if comment:
            await send_message(chat_id, comment)
        return

    if text.startswith("/bonus ") and is_group_admin(phone, group_id):
        parts = text[7:].strip().split(" ", 2)
        if len(parts) >= 2 and parts[1].lstrip("-").isdigit():
            b_name = parts[0]
            b_points = int(parts[1])
            b_reason = parts[2] if len(parts) > 2 else "ручной бонус"
            b_student = find_by_name(b_name, group_id)
            if b_student:
                add_bonus(b_student["id"], group_id, get_date(), b_points, "bonus", subcategory=b_reason[:50], note=b_reason)
                sign = "+" if b_points >= 0 else ""
                await send_message(chat_id,
                    "✅ " + b_name + ": " + sign + str(b_points) + " баллов\nПричина: " + b_reason)
            else:
                await send_message(chat_id, "Студент «" + b_name + "» не найден")
        else:
            await send_message(chat_id, "Формат: /bonus Имя 10 причина\nПример: /bonus Бакыт 5 победил в конкурсе")
        return

    # ── Отметка присутствия на уроке (u / у) ─────────────────────────────────
    text_lower = text.strip().lower()
    if text_lower in ("u", "у"):
        s_self = find_by_phone(phone, group_id)
        if s_self:
            if not has_attendance_this_week(s_self["id"], group_id):
                add_bonus(s_self["id"], group_id, get_date(), 5, "attendance", "online")
                await send_message(chat_id, T("present", glang, name=s_self["name"]))
        return

    s = find_by_phone(phone, group_id)

    # Устаз не проходит через студенческий флоу — если он также студент, пропускаем
    if is_group_admin(phone, group_id) and not s:
        return

    if not s:
        return

    # ── Прямое обращение к Ясиру ──────────────────────────────────────────────
    yassir_question = detect_yassir(text)
    if yassir_question is not None:
        if not yassir_question:
            await send_message(chat_id, T("yassir_listening", glang))
            return
        answer = await ai.answer_question(
            yassir_question, _build_reference_for_question(yassir_question),
            group["title"] or chat_id, phone, group_id, s["name"],
            is_ustaz=is_group_admin(phone, group_id)
        )
        await send_message(chat_id, "🤖 Ясир:\n" + answer)
        return

    # ── Определяем тип сообщения и задания ────────────────────────────────────
    tasks_done = {k: False for k in TASK_KEYS}
    legend = "\n".join(task_name(k, glang) for k in group_tasks)

    if is_media:
        if not text or is_checkmarks_only(text):
            return
        tasks_done = check_text(text)
    elif is_checkmarks_only(text):
        await send_message(chat_id, T("ask_words", glang, name=s["name"], legend=legend))
        return
    else:
        tasks_done = check_text(text)

    score = sum(1 for k in group_tasks if tasks_done.get(k))

    if score == 0:
        # ── Уважительная причина → 1 балл (только если это не отчёт) ────────
        is_excuse = any(w in text.strip().lower() for w in EXCUSE_WORDS)
        if is_excuse:
            with db() as c:
                already_excuse = c.execute(
                    "SELECT 1 FROM score_events"
                    " WHERE student_id=? AND group_id=? AND date=? AND category='excuse'",
                    (s["id"], group_id, get_date())
                ).fetchone()
            if not already_excuse:
                add_bonus(s["id"], group_id, get_date(), 1, "excuse")
                await send_message(chat_id,
                    "✅ " + s["name"] + ", уважительная причина принята.\nЗасчитан 1 балл. Берегите себя! 🤲")
            else:
                await send_message(chat_id, "ℹ️ " + s["name"] + ", причина уже засчитана сегодня. 🤲")
            return
        if not is_media:
            answer = await ai.answer_if_relevant(
                text, _build_reference_for_question(text),
                group["title"] or chat_id, phone, group_id, s["name"],
                is_ustaz=is_group_admin(phone, group_id)
            )
            if answer:
                await send_message(chat_id, "🤖 Ясир:\n" + answer)
        return

    # ── ИИ-проверка в фоне ────────────────────────────────────────────────────
    if not is_media and len(text.strip()) > 10:
        checks = []
        if tasks_done.get("j"):
            checks.append("tajweed (mahraj and sifat of letters)")
        if tasks_done.get("n"):
            checks.append("arabic grammar (nahw/irab)")
        if tasks_done.get("t"):
            checks.append("mufradat (arabic word spelling and translation accuracy)")
        if tasks_done.get("h"):
            checks.append("hadith (arabic word spelling and translation accuracy)")
        # Верификация только если есть арабский текст — иначе нечего проверять
        if _has_arabic(text):
            asyncio.create_task(_verify_and_reply(
                chat_id, text, group["title"] or chat_id, phone, group_id, s["name"], checks, glang, message_id))

    # ── Засчитываем отчёт ─────────────────────────────────────────────────────
    prev = get_today_report(s["id"], group_id)
    prev_done = set()
    if prev:
        prev_done = {k for k in group_tasks if prev[k]}
    was_complete = (len(prev_done) == len(group_tasks))

    if prev:
        for key in group_tasks:
            if prev[key]:
                tasks_done[key] = True
    save_report(s["id"], group_id, get_date(), tasks_done)

    now_done = {k for k in group_tasks if tasks_done.get(k)}
    new_tasks = now_done - prev_done
    missing = [k for k in group_tasks if not tasks_done.get(k, False)]
    wait_list = [DEFAULT_TASKS[k] for k in missing]
    now_complete = (len(missing) == 0)

    if was_complete and not new_tasks:
        await send_message(chat_id, T("already_all", glang, name=s["name"]))
        return

    if not new_tasks:
        await send_message(chat_id, T("already_counted", glang, name=s["name"]))
        return

    new_names = [SHORT_TASKS.get(k, DEFAULT_TASKS[k]) for k in group_tasks if k in new_tasks]
    reply = T("accepted", glang, name=s["name"]) + " " + ", ".join(new_names)
    if wait_list:
        reply += "\n" + T("remaining", glang) + " " + ", ".join(wait_list)
    if now_complete:
        reply += "\n" + T("all_done", glang)
    await send_message(chat_id, reply)

