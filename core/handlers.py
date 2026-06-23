import asyncio
import logging

from config import ADMIN_PHONES
from core.content import (
    TASK_KEYS, DEFAULT_TASKS, ONLINE_WORDS, EXCUSE_WORDS, PROGRAM_INFO
)
from core.i18n import T, get_group_lang, LANG_NAMES
from core.tg import send_message
import core.ai as ai
from core.db import (
    get_group, save_group, get_group_tasks, update_group_tasks, update_group_lang,
    update_group_type, update_group_fallback, update_group_summary,
    get_all_groups, get_students, find_by_phone, find_by_name, add_student,
    register_student, deactivate_student, rename_student, remove_all_students,
    add_group_admin, remove_group_admin, get_group_admins,
    is_pending_name, set_pending_name, get_pending_text, clear_pending_name,
    get_today_report, save_report, check_text, count_checkmarks, is_checkmarks_only,
    get_streak_days, get_skip_count_month, add_bonus,
    start_online_lesson, mark_attendance,
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
    "/remove Имя — убрать студента\n"
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
    "/admin +телефон — назначить устаза группы\n"
    "/unadmin +телефон — убрать устаза\n"
    "/admins — список устазов\n"
    "/removeall — удалить всех студентов\n\n"
    "/teach текст — обучить бота\n"
    "/knowledge — что знает бот\n"
    "/forget N — удалить знание N\n\n"
    "/отчёт Имя — засчитать отчёт вручную"
)


def _section_student(group_tasks, gtype):
    task_lines = "\n".join(
        str(i + 1) + ". " + _TASK_NAMES[k]
        for i, k in enumerate(group_tasks) if k in _TASK_NAMES
    )
    limit_info = ""
    if gtype == "pro":
        limit_info = "\n⚠️ Pro-группа: пропуск 14 дней → Тадаббур"
    elif gtype == "relaxed":
        limit_info = "\n📅 Расслабленная: пропуск 30 дней → Тадаббур"
    return (
        "📚 КАК СДАВАТЬ ОТЧЁТ\n"
        "Пиши что выполнил:\n" + task_lines + "\n"
        "За каждое задание +1 балл 💎\n\n"
        "⛔ Уважительная причина:\nболею / уважительная / узр / причина есть\n"
        "📡 Онлайн урок: напиши +\n\n"
        "/mystats — твоя статистика\n"
        "/rating — рейтинг группы\n"
        "Ясир, ...? — задай вопрос боту"
        + limit_info
    )


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
    return phone in ADMIN_PHONES


def is_group_admin(phone, group_id):
    if phone in ADMIN_PHONES:
        return True
    return phone in get_group_admins(group_id)


def detect_yassir(text):
    t = text.strip()
    low = t.lower()
    for v in ["ясир", "ясыр", "yassir", "yasir", "yassır", "яссир"]:
        if low.startswith(v):
            return t[len(v):].lstrip(" ,!:-—?")
    return None


def get_full_program_info():
    extra = get_knowledge()
    if not extra:
        return PROGRAM_INFO
    lines = [PROGRAM_INFO, "\nДОПОЛНИТЕЛЬНЫЕ ПРАВИЛА ОТ УСТАЗА:"]
    for row in extra:
        lines.append("- " + row["text"])
    return "\n".join(lines)


def _has_arabic(text):
    return any("؀" <= ch <= "ۿ" for ch in text)


async def _verify_and_reply(chat_id, text, group_title, phone, group_id, name, checks):
    try:
        writing_section = ""
        if _has_arabic(text):
            checks = list(checks) + ["письмо (хуруфы и соединение)"]
            writing_section = (
                "\n✍️ ПИСЬМО — ПОЛНАЯ ПРОВЕРКА НАПИСАНИЯ АРАБСКИХ СЛОВ:\n"
                "Проверяй каждое арабское слово ЦЕЛИКОМ:\n"
                "1. ХАМЗА — на правильной подставке (ئ ؤ أ إ آ ء) по огласовке\n"
                "2. БУКВЫ — все ли буквы на месте, нет ли пропущенных/лишних\n"
                "3. СОЕДИНЕНИЕ — буквы НЕ соединяющиеся слева: ا د ذ ر ز و — после них следующая буква пишется отдельно\n"
                "4. ОГЛАСОВКИ (харакят) — фатха/кясра/дамма/сукун/шадда/танвин на правильных местах\n"
                "5. ТА-МАРБУТА (ة) vs та обычная (ت) — в конце слова\n"
                "6. АЛИФ-МАКСУРА (ى) vs йа (ي) — в конце слова\n"
                "7. ХАРФЫ МАДДА — длинные гласные ا و ي на месте\n"
                "8. ЛЯМ-АЛИФ (لا) — правильное написание\n"
                "9. ПЕРЕВОД — точность значения слова\n\n"
                "ПРИМЕРЫ ОШИБОК:\n"
                "• جءت → правильно جِئْتَ (хамза на йа)\n"
                "• الرحمن без алифа → الرَّحْمَٰن\n"
                "• ة вместо ت: رحمة/رحمت\n"
                "• ى вместо ي: علي/على (разные слова!)\n\n"
                "ОГЛАСОВКИ (харакат) без арабского текста НЕ ТРЕБУЙ — студент может писать без них.\n"
                "Если написание ВЕРНО — не упоминай раздел письмо вообще.\n"
            )

        system = (
            "Ты учитель Корана Ясир. Проверь ТОЛЬКО " + ", ".join(checks) + " в сообщении студента.\n\n"
            "🚨 ГЛАВНОЕ ПРАВИЛО ПРОВЕРКИ:\n"
            "Прежде чем заявить об ошибке — НАЙДИ это правило в СПРАВОЧНИКЕ ниже и сверься БУКВА В БУКВУ.\n"
            "Если ответ студента СОВПАДАЕТ со справочником — это ВЕРНО, НЕ исправляй.\n"
            "НЕ полагайся на свою память — справочник ГЛАВНЕЕ твоих знаний.\n"
            "Если правила нет в справочнике и ты не уверен на 100% — НЕ делай замечание.\n\n"
            "СТРОГОЕ РАЗДЕЛЕНИЕ:\n"
            "📖 ТАДЖВИД: проверяй ТОЛЬКО махрадж (место выхода буквы) и сифат (свойство). "
            "⚠️ КРИТИЧЕСКИ ВАЖНО — не путай буквы:\n  ح (ха) → СЕРЕДИНА горла\n  خ (ха-кх) → КОНЕЦ горла. ح ≠ خ!\n\n"
            "📝 МУФРАДАТ: проверяй ТОЛЬКО БУКВЫ арабского слова и точность перевода. "
            "ОГЛАСОВКИ (харакат) НЕ ТРЕБУЙ — это НЕ ошибка! Проверяй только хуруф (согласные).\n\n"
            "📚 НАХВ: проверяй ТОЛЬКО ИЪРАБ (конечную огласовку) и название члена предложения. "
            "ТАБЛИЦА: فاعل→رفع, مفعول به→نصب, مضاف إليه→جر, اسم كان→رفع, خبر كان→نصب.\n\n"
            + writing_section +
            "ПРАВИЛА ОТВЕТА:\n"
            "- Если всё ВЕРНО → ответь ровно одним словом: ВЕРНО\n"
            "- Если есть ОШИБКА → МАКСИМУМ 3 строки: что неверно и как правильно\n"
            "- ЗАПРЕЩЕНО: длинные объяснения, лекции, хвалебные фразы\n\n"
            "СПРАВОЧНИК:\n" + get_full_program_info()
        )
        prompt = "Сообщение студента " + name + ":\n" + text
        result = await ai.ask_ai(prompt, system=system)
        if result and "ВЕРНО" not in result.upper()[:20]:
            await send_message(chat_id, "🤖 Ясир (проверка):\n" + result)
        elif result and "ВЕРНО" in result.upper()[:20]:
            await send_message(chat_id, "✅")
    except Exception as e:
        log.error("verify error: %s", e)


async def process_message(chat_id, sender, text, sender_name="", is_media=False, reply_to_id=None):
    phone = extract_phone(sender)
    text = (text or "").strip()
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
                "/remove Имя — удалить\n"
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
                    "SELECT COUNT(DISTINCT sid) FROM reports WHERE date=?", (get_date(),)
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

    # ── Личка только для супер-админов ───────────────────────────────────────
    if not is_group:
        if not is_admin(phone):
            await send_message(chat_id, "Ассаляму алейкум! 🕌\nПиши в своей группе.")
            return
        if text and not text.startswith("/"):
            answer = await ai.answer_question(
                text, get_full_program_info(), "личка суперадмина", phone, None, sender_name
            )
            await send_message(chat_id, answer)
        return

    group = get_group(chat_id)

    if text == "/setgroup":
        if not is_admin(phone):
            return
        from core.tg import tg_call
        chat_info = await tg_call("getChat", {"chat_id": int(chat_id)})
        title = (chat_info or {}).get("result", {}).get("title", sender_name or chat_id)
        save_group(chat_id, title)
        await send_message(chat_id,
            "✅ Группа зарегистрирована: " + str(title) + "\n"
            "По умолчанию тип: relaxed, 3 задания (m,r,t).\n"
            "Сменить тип: /settype pro|relaxed|tadabbur\n"
            "Сменить задания: /settasks m,r,t,j"
        )
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
    if not is_group_admin(phone, group_id) and not text.startswith("/"):
        s_reg = find_by_phone(phone, group_id)
        if not s_reg:
            if is_pending_name(phone, group_id):
                import re as _re
                new_name = text.strip()
                # Если ещё не сохранён отчёт — проверим, не отчёт ли это сообщение
                if not get_pending_text(phone, group_id):
                    td_pre = check_text(new_name)
                    if sum(1 for k in group_tasks if td_pre.get(k)) > 0:
                        set_pending_name(phone, group_id, new_name)
                        await send_message(chat_id, T("ask_name", glang))
                        return
                if len(new_name) < 2 or len(new_name) > 40 or not _re.search(r"[a-zA-Zа-яА-ЯёЁЀ-ӿ؀-ۿЀ-ԯ]", new_name):
                    await send_message(chat_id, T("ask_name_again", glang))
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
                for ap in ADMIN_PHONES:
                    await send_message(ap, "👤 " + new_name + " зарегистрировался в «" + (group["title"] or str(chat_id)) + "»")
                if saved and saved.strip():
                    td = check_text(saved)
                    sc = sum(1 for k in group_tasks if td.get(k))
                    if sc > 0:
                        save_report(sid, group_id, get_date(), td)
                        done_list = [_TASK_NAMES[k] for k in group_tasks if td.get(k) and k in _TASK_NAMES]
                        await send_message(chat_id, "📖 Засчитан отчёт из первого сообщения:\n" + "\n".join("✅ " + n for n in done_list))
                return
            else:
                # Уже зарегистрирован в другой группе — авторегистрация
                existing_user = find_user_by_phone(phone)
                if existing_user:
                    add_student(existing_user["name"], group_id, phone)
                    await send_message(chat_id, T("registered_group", glang, name=existing_user["name"]))
                    return
                # Первый раз в системе — спрашиваем имя
                set_pending_name(phone, group_id, text)
                greeting = ("Ассаляму алейкум, " + sender_name + "! 🌙\n") if sender_name else "Ассаляму алейкум! 🌙\n"
                await send_message(chat_id, greeting + T("ask_name", glang))
                return

    # ── Управление группой (только группа-админ) ───────────────────────────────
    if (text.startswith("/admin") or text == "/admin") and phone in ADMIN_PHONES:
        new_admin = None
        new_admin_label = ""
        # 1. Реплай → берём user_id из реплая
        if reply_to_id:
            new_admin = str(reply_to_id)
            new_admin_label = "из реплая"
        else:
            arg = text[6:].strip()
            if arg.startswith("@"):
                # 2. @username → ищем в кеше
                uid = lookup_username(arg)
                if uid:
                    new_admin = uid
                    new_admin_label = arg
                else:
                    await send_message(chat_id, "Не нашёл " + arg + " — он должен написать хоть раз в группу. Или ответь реплаем на его сообщение и напиши /admin")
                    return
            else:
                clean = arg.replace("+", "").replace(" ", "")
                if clean.isdigit():
                    # 3. Числовой Telegram ID
                    new_admin = clean
                    new_admin_label = "ID " + clean
                elif arg:
                    # 4. Поиск по имени — сначала кэш участников этой группы
                    cache_hits = lookup_by_name_in_chat(chat_id, arg)
                    if len(cache_hits) == 1:
                        new_admin = cache_hits[0][1]
                        new_admin_label = cache_hits[0][0]
                    elif len(cache_hits) > 1:
                        names = ", ".join(h[0] for h in cache_hits)
                        await send_message(chat_id, "Нашёл несколько: " + names + "\nУточни имя точнее.")
                        return
                    else:
                        # Кэша нет — ищем среди студентов БД
                        seen = set()
                        matches = []
                        for g in [{"id": group_id}] + [g for g in get_all_groups() if g["id"] != group_id]:
                            for s in get_students(g["id"]):
                                if arg.lower() in s["name"].lower() and s["phone"] and s["phone"] not in seen:
                                    seen.add(s["phone"])
                                    matches.append(s)
                        if len(matches) == 1:
                            new_admin = matches[0]["phone"]
                            new_admin_label = matches[0]["name"]
                        elif len(matches) > 1:
                            names = ", ".join(s["name"] for s in matches)
                            await send_message(chat_id, "Нашёл несколько: " + names + "\nУточни имя точнее.")
                            return
                        else:
                            await send_message(chat_id, "Не нашёл «" + arg + "».\nПусть напишет что-нибудь в группу, потом попробуй снова.")
                            return
        if new_admin:
            add_group_admin(group_id, new_admin)
            await send_message(chat_id, "✅ Назначен устазом группы (" + new_admin_label + ")")
        else:
            await send_message(chat_id, "Как назначить устаза:\n• Ответь реплаем на его сообщение → /admin\n• /admin @username\n• /admin Имя\n• /admin 123456789")
        return

    if (text.startswith("/unadmin") or text == "/unadmin") and phone in ADMIN_PHONES:
        target = None
        label = ""
        if reply_to_id:
            target = str(reply_to_id)
            label = "из реплая"
        else:
            arg = text[8:].strip()
            if arg.startswith("@"):
                uid = lookup_username(arg)
                if uid:
                    target = uid
                    label = arg
                else:
                    await send_message(chat_id, "Не нашёл " + arg + " — он должен написать хоть раз в группу.")
                    return
            else:
                clean = arg.replace("+", "").replace(" ", "")
                if clean.isdigit():
                    target = clean
                    label = "ID " + clean
                elif arg:
                    cache_hits = lookup_by_name_in_chat(chat_id, arg)
                    if len(cache_hits) == 1:
                        target = cache_hits[0][1]
                        label = cache_hits[0][0]
                    elif len(cache_hits) > 1:
                        await send_message(chat_id, "Нашёл несколько: " + ", ".join(h[0] for h in cache_hits) + "\nУточни имя.")
                        return
                    else:
                        matches = [s for s in get_students(group_id) if arg.lower() in s["name"].lower() and s["phone"]]
                        if len(matches) == 1:
                            target = matches[0]["phone"]
                            label = matches[0]["name"]
                        else:
                            await send_message(chat_id, "Не нашёл «" + arg + "».\nПопробуй реплаем или /unadmin @username")
                            return
        if target:
            remove_group_admin(group_id, target)
            await send_message(chat_id, "✅ Убран из устазов группы (" + label + ")")
        else:
            await send_message(chat_id, "Как убрать устаза:\n• Реплай на его сообщение → /unadmin\n• /unadmin @username\n• /unadmin Имя")
        return

    if text == "/admins":
        admins = get_group_admins(group_id)
        lines = ["👤 Админы группы:"]
        lines.append("Главные: " + ", ".join(ADMIN_PHONES))
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
        if gtype in ("pro", "relaxed", "tadabbur"):
            update_group_type(chat_id, gtype)
            type_desc = {
                "pro": "Про-группа (14 дней без отчёта → Тадаббур)",
                "relaxed": "Расслабленная (30 дней → Тадаббур)",
                "tadabbur": "Тадаббур — пространство красоты и смыслов Корана (не учебная группа)"
            }
            await send_message(chat_id, "✅ Тип группы: " + type_desc[gtype])
        else:
            await send_message(chat_id, "Доступные типы:\n/settype pro\n/settype relaxed\n/settype tadabbur")
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

    # ── Студенты ──────────────────────────────────────────────────────────────
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
                SELECT u.name, COALESCE(SUM(r.score),0) as total, COUNT(r.id) as days
                FROM users u
                JOIN user_groups ug ON u.id=ug.user_id
                LEFT JOIN reports r ON u.id=r.sid AND r.date>=? AND r.group_id=?
                WHERE ug.group_id=? AND ug.role='student' AND ug.active=1
                GROUP BY u.id ORDER BY total DESC
            """, (week_ago, group_id, group_id)).fetchall()
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
            sections.append(_section_student(group_tasks, group["group_type"] or "relaxed"))
        if is_group_admin(phone, group_id):
            sections.append(_SECTION_GRP_ADMIN)
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
                "SELECT COALESCE(SUM(score),0) as total, COUNT(id) as days FROM reports WHERE sid=?",
                (s_check["id"],)
            ).fetchone()
            bonus_row = c.execute(
                "SELECT COALESCE(SUM(points),0) as bonus FROM bonus_points WHERE sid=?",
                (s_check["id"],)
            ).fetchone()
            rank_rows = c.execute("""
                SELECT u.id, COALESCE(SUM(r.score),0)+COALESCE(b.bonus,0) as grand
                FROM users u
                JOIN user_groups ug ON u.id=ug.user_id
                LEFT JOIN reports r ON r.sid=u.id
                LEFT JOIN (SELECT sid, SUM(points) as bonus FROM bonus_points GROUP BY sid) b ON b.sid=u.id
                WHERE ug.group_id=? AND ug.role='student' AND ug.active=1
                GROUP BY u.id ORDER BY grand DESC
            """, (group_id,)).fetchall()
        total_score = (total_row["total"] or 0) + (bonus_row["bonus"] or 0)
        days_done = total_row["days"] or 0
        rank = next((i + 1 for i, r in enumerate(rank_rows) if r["id"] == s_check["id"]), "?")
        today_rep = get_today_report(s_check["id"])
        today_done = sum(1 for k in group_tasks if today_rep and today_rep[k]) if today_rep else 0
        gtype = group["group_type"] or "relaxed"
        limit_days = 14 if gtype == "pro" else 30

        lines = [
            T("mystats_title", glang, name=s_check["name"]),
            T("mystats_streak", glang, n=streak),
            T("mystats_rank", glang, n=rank),
            T("mystats_points", glang, n=total_score),
            T("mystats_days", glang, n=days_done),
            T("mystats_skips", glang, n=skips_month, limit=limit_days),
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
                add_bonus(b_student["id"], group_id, get_date(), b_points, "manual_" + get_date() + "_" + b_reason[:20])
                sign = "+" if b_points >= 0 else ""
                await send_message(chat_id,
                    "✅ " + b_name + ": " + sign + str(b_points) + " баллов\nПричина: " + b_reason)
            else:
                await send_message(chat_id, "Студент «" + b_name + "» не найден")
        else:
            await send_message(chat_id, "Формат: /bonus Имя 10 причина\nПример: /bonus Бакыт 5 победил в конкурсе")
        return

    # ── Уважительная причина → 1 балл ─────────────────────────────────────────
    is_excuse = any(w in text.strip().lower() for w in EXCUSE_WORDS)
    s_pre = find_by_phone(phone, group_id)
    if is_excuse and s_pre:
        with db() as c:
            already_excuse = c.execute(
                "SELECT 1 FROM bonus_points WHERE sid=? AND date=? AND reason='excuse'",
                (s_pre["id"], get_date())
            ).fetchone()
        if not already_excuse:
            add_bonus(s_pre["id"], group_id, get_date(), 1, "excuse")
            await send_message(chat_id,
                "✅ " + s_pre["name"] + ", уважительная причина принята.\nЗасчитан 1 балл. Берегите себя! 🤲")
        else:
            await send_message(chat_id, "ℹ️ " + s_pre["name"] + ", причина уже засчитана сегодня. 🤲")
        return

    # ── Отметка присутствия (+) ────────────────────────────────────────────────
    text_lower = text.strip().lower()
    is_online_word = text_lower in [w.lower() for w in ONLINE_WORDS] or text.strip() == "+"
    if is_online_word and not is_group_admin(phone, group_id):
        s_self = find_by_phone(phone, group_id)
        if s_self:
            lesson = start_online_lesson(group_id)
            with db() as c:
                already = c.execute(
                    "SELECT 1 FROM attendance WHERE sid=? AND lesson_id=?",
                    (s_self["id"], lesson["id"])
                ).fetchone()
            if not already:
                mark_attendance(s_self["id"], lesson["id"])
                add_bonus(s_self["id"], group_id, get_date(), 5, "online_lesson")
                await send_message(chat_id, T("present", glang, name=s_self["name"]))
            return

    # ── Отметка присутствия списком (от учителя) ──────────────────────────────
    def try_mark_attendance(msg_text):
        chunks = msg_text.replace("\n", ",").replace(".", ",").split(",")
        found_students, leftover = [], []
        for chunk in chunks:
            nm = chunk.strip()
            if not nm:
                continue
            st = find_by_name(nm, group_id)
            if st:
                found_students.append(st)
            else:
                leftover.append(nm)
        return found_students, leftover

    found, leftover = try_mark_attendance(text)
    has_task_word = any(v for v in check_text(text).values())
    is_yassir = detect_yassir(text) is not None
    junk = [x for x in leftover if len(x) > 2 and x.lower() not in
            ("был", "была", "были", "и", "да", "все", "тут", "есть", "присутствовал", "присутствовали")]
    is_attendance_list = (len(found) >= 2) or (len(found) >= 1 and is_group_admin(phone, group_id))
    if found and is_attendance_list and not has_task_word and not is_yassir and not junk:
        lesson = start_online_lesson(group_id)
        marked = []
        for st in found:
            mark_attendance(st["id"], lesson["id"])
            add_bonus(st["id"], group_id, get_date(), 5, "online_lesson")
            marked.append(st["name"])
        await send_message(chat_id,
            "📡 Онлайн урок отмечен!\n\n✅ Присутствовали (+5 баллов):\n" +
            "\n".join("• " + n for n in marked))
        return

    s = find_by_phone(phone, group_id)

    # Admins who are not students in this group don't submit reports
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
            yassir_question, get_full_program_info(),
            group["title"] or chat_id, phone, group_id, s["name"]
        )
        await send_message(chat_id, "🤖 Ясир:\n" + answer)
        return

    # ── Определяем тип сообщения и задания ────────────────────────────────────
    tasks_done = {k: False for k in TASK_KEYS}
    legend = "\n".join(DEFAULT_TASKS[k] for k in group_tasks)

    if is_media:
        if text and not is_checkmarks_only(text) and len(text.strip()) > 3:
            tasks_done = check_text(text)
        else:
            return
    elif is_checkmarks_only(text):
        await send_message(chat_id, T("ask_words", glang, name=s["name"], legend=legend))
        return
    else:
        tasks_done = check_text(text)

    score = sum(1 for k in group_tasks if tasks_done.get(k))

    # Вопрос к Ясиру (есть "?")
    is_question = ("?" in text and score == 0)
    if is_question and not is_media:
        answer = await ai.answer_question(
            text, get_full_program_info(),
            group["title"] or chat_id, phone, group_id, s["name"]
        )
        await send_message(chat_id, "🤖 Ясир:\n" + answer)
        return

    if score == 0:
        return

    # ── ИИ-проверка в фоне ────────────────────────────────────────────────────
    if not is_media and len(text.strip()) > 10:
        checks = []
        if tasks_done.get("j"):
            checks.append("таджвид")
        if tasks_done.get("n"):
            checks.append("грамматику (нахв)")
        if tasks_done.get("t"):
            checks.append("муфрадат (написание арабских слов и перевод)")
        # Письмо проверяется всегда когда есть арабский текст
        if checks or _has_arabic(text):
            asyncio.create_task(_verify_and_reply(
                chat_id, text, group["title"] or chat_id, phone, group_id, s["name"], checks))

    # ── Засчитываем отчёт ─────────────────────────────────────────────────────
    prev = get_today_report(s["id"])
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
        reply = T("already_counted", glang, name=s["name"])
        if wait_list:
            reply += "\n\n" + T("still_left", glang) + "\n" + "\n".join("⬜ " + n for n in wait_list)
        await send_message(chat_id, reply)
        return

    new_names = [DEFAULT_TASKS[k] for k in group_tasks if k in new_tasks]
    reply = T("accepted", glang, name=s["name"]) + "\n\n"
    reply += T("counted_today", glang) + "\n" + "\n".join("✅ " + n for n in new_names)
    if wait_list:
        reply += "\n\n" + T("still_left", glang) + "\n" + "\n".join("⬜ " + n for n in wait_list)
        reply += "\n\n" + T("keep_going", glang)
    if now_complete:
        reply += "\n\n" + T("all_done", glang)
    await send_message(chat_id, reply)

    if now_complete and not was_complete:
        await send_message(chat_id, T("all_done_praise", glang, name=s["name"]))
