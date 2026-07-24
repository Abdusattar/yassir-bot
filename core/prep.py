"""
Логика подготовительной группы (group_type='prep').

Проверка идёт ежедневно по каждому активному студенту prep:
  ≥5 дней с отчётами (в любой момент, не дожидаясь 14 дней) →
                        объявление в саму prep-группу (мотивация остальным) +
                        студенту в личку вопрос с кнопками "знаешь ли хотя бы
                        1 джуз наизусть?" (решение Умар устаза 24.07.2026).
                        По ответу бот САМ подбирает группу: знает ≥1 джуз →
                        конкретная группа N-1, не знает → наименее заполненная
                        relaxed нужного языка - и шлёт студенту в личку
                        ссылку-приглашение. Устаз
                        больше не участвует, кроме редкого случая, когда
                        подходящей группы со ссылкой не нашлось (см.
                        handle_juz_answer). Из prep деактивируется и
                        физически кикается только когда студент реально
                        станет активным в pro/relaxed группе (см.
                        announce_prep_graduate_arrival — срабатывает по
                        факту вступления по ссылке, а не заранее).
  <5 дней к дедлайну   → остаётся в Тадаббуре, деактивируется из prep
                        и физически кикается (мягко, ban+unban) из чата —
                        иначе дыра авторегистрации: следующим же сообщением
                        в этом чате студент молча вернётся активным (было
                        реальным инцидентом, см. wiki/prep_group.md).
                        Дедлайн — 14 дней с joined_date, но если студент успел
                        сдать хотя бы 1 отчёт (значит реально начал), даём ему
                        +5 дней (до 19) — решение пользователя от 20.07.2026:
                        не резать тех, кто уже втянулся, только за то, что не
                        успел набрать все 5 дней ровно к 14-му дню.
"""
import logging

from config import IS_FEMALE
from core.db import (
    db, get_prep_students_active, count_report_days_since, add_bonus,
    get_tadabbur_group, add_student, find_by_phone, deactivate_student,
    clear_pending_prep_return, prep_days_done, get_regular_group_sizes,
    get_best_group_for_transfer, get_group_by_title, get_dm_ok_by_phone,
)
from core.i18n import T, get_group_lang
from core.tg import send_message, ban_member, unban_member, send_message_with_buttons

log = logging.getLogger(__name__)

PREP_DAYS = 14
PREP_MIN_DAYS = 5
PREP_EXTENSION_DAYS = 5  # доп. дни к дедлайну, если студент сдал ≥1 отчёт

# Кому лично уходит уведомление о выпускнике подготовительной — один
# конкретный человек на профиль, не все супер-админы (решение 23.07.2026,
# см. докстринг модуля выше).
_PREP_GRADUATE_ADMIN_ID = "5342232498" if IS_FEMALE else "7666229019"  # Зейнеб / Умар устаз

# Кто знает хотя бы 1 джуз наизусть - идёт в конкретную группу N-1, а не в
# "любую наименее заполненную pro" (уточнение Умар устаза 24.07.2026).
_PREP_JUZ_KNOWN_TARGET_TITLE = "N-1"


async def check_prep_students():
    """Вызывается ежедневно в 21:00 рядом с check_transfers."""
    students = get_prep_students_active()
    for s in students:
        uid = s["phone"]
        group_id = s["group_id"]
        joined = s["joined_date"]
        glang = _group_lang(group_id)

        days_done = count_report_days_since(s["id"], group_id, joined)
        elapsed = s["elapsed"] or 0

        if days_done >= PREP_MIN_DAYS:
            if not _has_prep_offer(s["id"], group_id):
                # Объявление в группу — один раз (мотивация остальным)
                add_bonus(s["id"], group_id, joined, 0, "prep_offer")
                await send_message(s["chat_id"], T("prep_success_group", glang, name=s["name"], days=days_done))

            if not _has_juz_answer(s["id"], group_id):
                # Вопрос студенту в личку про джуз — повторяем КАЖДУЮ проверку,
                # пока не ответит (не одноразовый флаг!). Иначе если бот ещё
                # не может писать в личку (студент сам не открывал диалог с
                # ботом — Forbidden: bot can't initiate conversation), вопрос
                # тихо не доходит, а студент остаётся зависшим навсегда
                # (тот же класс бага, что уже ловили сегодня на Мураде вручную,
                # см. feedback про add_bonus до отправки — 24.07.2026).
                await send_juz_question(uid, s["name"], glang, days_done, s["chat_id"])
                log.info("prep check: student=%s days_done=%d → juz question (re)sent", s["name"], days_done)
        else:
            deadline = PREP_DAYS + (PREP_EXTENSION_DAYS if days_done >= 1 else 0)
            if elapsed < deadline:
                continue
            _deactivate_from_prep(s["id"], group_id)
            # Гарантируем, что "остаёшься в Тадаббуре" — правда, а не просто текст
            tadabbur = get_tadabbur_group()
            already_in_tadabbur = tadabbur and find_by_phone(uid, tadabbur["id"])
            if tadabbur and not already_in_tadabbur:
                add_student(s["name"], tadabbur["id"], uid)
            fail_text = T("prep_failed", glang, name=s["name"], days=days_done)
            if tadabbur and not already_in_tadabbur and tadabbur["invite_link"]:
                fail_text += "\n\n👉 " + tadabbur["invite_link"]
            await send_message(uid, fail_text)
            await send_message(s["chat_id"], T("prep_failed_group", glang, name=s["name"], days=days_done))
            try:
                await ban_member(s["chat_id"], uid)
                await unban_member(s["chat_id"], uid)
            except Exception as e:
                log.error("prep fail kick error student=%s chat=%s: %s", s["name"], s["chat_id"], e)
            log.info("prep check: student=%s days_done=%d < %d after %d days (deadline=%d) → failed, kicked", s["name"], days_done, PREP_MIN_DAYS, elapsed, deadline)


async def send_prep_reminders():
    """
    Вызывается ежедневно утром (07:00).
    Для каждой prep-группы отправляет одно сообщение в группу:
    - список активных студентов (≥1 день за 14)
    - список пассивных студентов
    """
    with db() as c:
        prep_groups = c.execute(
            "SELECT id, chat_id, title, lang FROM groups WHERE group_type='prep' AND active=1"
        ).fetchall()

    for group in prep_groups:
        group_id = group["id"]
        chat_id = group["chat_id"]
        glang = group["lang"] or "ru"

        with db() as c:
            students = c.execute("""
                SELECT u.id, u.name, ug.joined_date,
                       julianday('now','localtime') - julianday(ug.joined_date) as elapsed
                FROM users u
                JOIN user_groups ug ON u.id=ug.user_id
                WHERE ug.group_id=? AND ug.role='student' AND ug.active=1
            """, (group_id,)).fetchall()

        if not students:
            continue

        active_names = []
        passive_names = []

        for s in students:
            days_done = count_report_days_since(s["id"], group_id, s["joined_date"])
            elapsed = int(s["elapsed"] or 0)
            if days_done >= 1:
                needed = max(0, PREP_MIN_DAYS - days_done)
                active_names.append((s["name"], days_done, needed))
            else:
                days_left = max(0, PREP_DAYS - elapsed)
                passive_names.append((s["name"], days_left))

        lines = []
        if active_names:
            if glang == "ky":
                lines.append("✅ Тапшырып жатышкандар — мыкты, улантыңыздар:")
            else:
                lines.append("✅ Сдают отчёты — так держать:")
            for name, done, needed in active_names:
                if glang == "ky":
                    if needed > 0:
                        lines.append(f"  • {name} — {done} күн тапшырды, өтүүгө {needed} күн калды")
                    else:
                        lines.append(f"  • {name} — {done} күн тапшырды, шарт аткарылды, өтүүнү күтөбүз")
                else:
                    if needed > 0:
                        lines.append(f"  • {name} — {done} дн. сдано, осталось {needed} дн. до перехода")
                    else:
                        lines.append(f"  • {name} — {done} дн. сдано, условие выполнено, ожидаем перехода")

        if passive_names:
            if lines:
                lines.append("")
            if glang == "ky":
                lines.append(f"⏳ Азырынча тапшырбагандар — даярдык мезгили кыска, ≥5 күн тапшыруу зарыл:")
            else:
                lines.append(f"⏳ Пока не сдавали — период короткий, нужно ≥5 дней для перехода:")
            for name, left in passive_names:
                if glang == "ky":
                    lines.append(f"  • {name} — мөөнөткө {left} күн калды, тапшырууну баштаңыз")
                else:
                    lines.append(f"  • {name} — осталось {left} дн. до дедлайна, начните сдавать")

        if lines:
            try:
                await send_message(chat_id, "\n".join(lines))
            except Exception as e:
                log.warning("prep reminder group=%s error: %s", chat_id, e)


async def announce_prep_graduate_arrival(chat_id, group_id, phone):
    """Вызывается когда известный студент становится активным в pro/relaxed
    группе (устаз вручную позвал его туда после прохождения подготовительной
    — решение пользователя 23.07.2026, без заранее выбранной целевой группы
    и без ссылки). Если студент сейчас активен в ЛЮБОЙ подготовительной —
    это и есть выпуск: кикаем его оттуда, объявляем в обоих чатах."""
    with db() as c:
        target_group = c.execute("SELECT group_type FROM groups WHERE id=?", (group_id,)).fetchone()
        if not target_group or (target_group["group_type"] or "relaxed") not in ("pro", "relaxed"):
            return  # не постоянная учебная группа — не считается выпуском

        u = c.execute("SELECT id FROM users WHERE phone=?", (phone,)).fetchone()
        if not u:
            return
        prep_row = c.execute("""
            SELECT ug.group_id as gid, g.chat_id, g.title, u2.name, ug.joined_date
            FROM user_groups ug
            JOIN groups g ON ug.group_id=g.id
            JOIN users u2 ON u2.id=ug.user_id
            WHERE ug.user_id=? AND ug.role='student' AND ug.active=1 AND g.group_type='prep'
            LIMIT 1
        """, (u["id"],)).fetchone()
    if not prep_row:
        return

    from_group_id = prep_row["gid"]
    from_chat_id = prep_row["chat_id"]
    name = prep_row["name"]

    # Защита от преждевременного "выпуска": условие (≥5 дней отчётов) должно
    # быть реально выполнено, а не просто "студент где-то стал активным".
    # Тот же prep_days_done, что и block_return_if_pending_prep в
    # core/transfers.py — единый критерий, не дублируем расчёт вручную.
    days_done = prep_days_done(phone)
    if days_done < PREP_MIN_DAYS:
        log.warning(
            "prep graduate arrival skipped: %s active in new group but only %d/%d days in prep",
            name, days_done, PREP_MIN_DAYS
        )
        return

    _deactivate_from_prep_by_group_id(phone, from_group_id)

    # Официальный выпуск подтверждён — снимаем маркер "кикнут за пропуски,
    # должен вернуться только через prep" (см. core/transfers.py,
    # block_return_if_pending_prep), иначе он остался бы true навсегда.
    clear_pending_prep_return(phone)

    tadabbur = get_tadabbur_group()
    if tadabbur:
        deactivate_student(u["id"], tadabbur["id"])

    new_glang = _group_lang(group_id)
    old_glang = _group_lang(from_group_id)
    new_title = _group_title(group_id)

    try:
        addr = "сёстры" if IS_FEMALE else "братья"
        await send_message(chat_id, T("prep_graduate_announce_new", new_glang, name=name, addr=addr))
    except Exception as e:
        log.warning("prep graduate new-group announce failed: %s", e)

    try:
        await send_message(from_chat_id, T("prep_graduate_announce_old", old_glang, name=name, title=new_title))
    except Exception as e:
        log.warning("prep graduate old-group announce failed: %s", e)

    # Физически кикаем из подготовительной — иначе дыра авторегистрации
    # (следующее же сообщение там молча вернёт активным студентом).
    try:
        await ban_member(from_chat_id, phone)
        await unban_member(from_chat_id, phone)
    except Exception as e:
        log.error("prep graduate kick from prep failed for %s in %s: %s", name, from_chat_id, e)

    log.info("prep graduate confirmed: %s arrived in group=%s (kicked from prep)", name, group_id)


async def remind_ustaz_about_graduate(phone):
    """Студент, уже выполнивший условие prep, сам написал боту в личку, пока
    ждёт перевода — считаем это напоминанием. С 24.07.2026 перевод полностью
    автоматический (решение Умар устаза): если вопрос про джуз ещё не задан -
    задаём сейчас; если уже отвечал - шлём ту же ссылку повторно (чтобы не
    перевыбирать группу заново и не сбивать студента другой ссылкой).
    Возвращает (name, lang) если что-то реально отправлено, иначе None."""
    with db() as c:
        row = c.execute("""
            SELECT u.id as uid, u.name, ug.group_id as gid, ug.joined_date, g.chat_id, g.title, g.lang
            FROM user_groups ug
            JOIN groups g ON ug.group_id=g.id
            JOIN users u ON u.id=ug.user_id
            WHERE u.phone=? AND ug.role='student' AND ug.active=1 AND g.group_type='prep'
            LIMIT 1
        """, (phone,)).fetchone()
    if not row:
        return None
    days_done = count_report_days_since(row["uid"], row["gid"], row["joined_date"])
    if days_done < PREP_MIN_DAYS:
        return None
    glang = row["lang"] or "ru"
    answer = _get_juz_answer(row["uid"], row["gid"])
    if answer:
        _, target_group_id = answer
        with db() as c:
            g = c.execute("SELECT invite_link FROM groups WHERE id=?", (target_group_id,)).fetchone()
        if g and g["invite_link"]:
            await _send_dm_or_group(phone, row["chat_id"], T("prep_juz_result", glang, link=g["invite_link"]))
    else:
        await send_juz_question(phone, row["name"], glang, days_done, row["chat_id"])
    log.info("prep graduate reminder: %s nudged (answer=%s)", row["name"], bool(answer))
    return (row["name"], glang)


def _group_sizes_text():
    """Список постоянных групп с количеством студентов - для запасного
    ручного уведомления устазу, если авто-подбор группы не сработал (24.07.2026)."""
    rows = get_regular_group_sizes()
    if not rows:
        return ""
    lines = ["", "📊 Студентов в группах:"]
    for r in rows:
        lines.append(f"  • {r['title']} ({r['group_type']}): {r['cnt']}")
    return "\n".join(lines)


async def send_juz_question(phone, name, glang, days_done, group_chat_id):
    """В личку, если студент уже жал Start боту (get_dm_ok_by_phone) - иначе
    в саму prep-группу (личка молча не дойдёт - Forbidden: bot can't initiate
    conversation, пока студент сам не откроет диалог). Идентичность тапнувшего
    проверяется в bot.py по uid, закодированному в callback_data - кнопки в
    группе видны и нажимаемы всем, не только адресату (24.07.2026)."""
    text = T("prep_juz_question", glang, name=name, days=days_done)
    buttons = [
        (T("prep_juz_yes_btn", glang), f"pjz:yes:{phone}"),
        (T("prep_juz_no_btn", glang), f"pjz:no:{phone}"),
    ]
    target_chat = phone if get_dm_ok_by_phone(phone) else group_chat_id
    await send_message_with_buttons(target_chat, text, buttons)


async def _send_dm_or_group(phone, group_chat_id, text):
    target_chat = phone if get_dm_ok_by_phone(phone) else group_chat_id
    await send_message(target_chat, text)


async def handle_juz_answer(phone, knows_juz):
    """Студент нажал кнопку (знает ли хотя бы 1 джуз наизусть) - решение
    Умар устаза 24.07.2026: знает → конкретная группа N-1, не знает →
    наименее заполненная relaxed того же языка, что подготовительная
    (кыргызская исключается сама собой, если студент не из кыргызской
    подготовительной). Бот сам шлёт ссылку в личку - дальше как при обычном
    вступлении по ссылке (announce_prep_graduate_arrival сработает при
    заходе в чат)."""
    with db() as c:
        row = c.execute("""
            SELECT u.id as uid, u.name, ug.group_id as gid, ug.joined_date, g.lang, g.chat_id
            FROM user_groups ug
            JOIN groups g ON ug.group_id=g.id
            JOIN users u ON u.id=ug.user_id
            WHERE u.phone=? AND ug.role='student' AND ug.active=1 AND g.group_type='prep'
            LIMIT 1
        """, (phone,)).fetchone()
    if not row:
        return  # уже не в подготовительной (например, повторный тап после перевода)
    if _has_juz_answer(row["uid"], row["gid"]):
        return  # уже отвечал - не обрабатываем повторно (защита от двойного тапа)

    glang = row["lang"] or "ru"
    if knows_juz:
        target_type = "N-1"
        target = get_group_by_title(_PREP_JUZ_KNOWN_TARGET_TITLE)
    else:
        target_type = "relaxed"
        target = get_best_group_for_transfer("relaxed", glang)
    if not target or not target["invite_link"]:
        # Нет подходящей группы со ссылкой - редкий случай, зовём устаза вручную
        await send_message(_PREP_GRADUATE_ADMIN_ID,
            "⚠️ " + row["name"] + ": не нашлось группы (" + target_type +
            ") со ссылкой-приглашением - определите вручную." +
            _group_sizes_text())
        log.warning("prep juz answer: no eligible '%s' group for %s", target_type, row["name"])
        return

    add_bonus(row["uid"], row["gid"], row["joined_date"], 0, "prep_juz_answer",
              subcategory=target_type, note=str(target["id"]))
    await _send_dm_or_group(phone, row["chat_id"], T("prep_juz_result", glang, link=target["invite_link"]))
    log.info("prep juz answer: %s → %s (group=%s)", row["name"], target_type, target["title"])


def _has_prep_offer(user_id, group_id):
    with db() as c:
        return c.execute(
            "SELECT 1 FROM score_events WHERE student_id=? AND group_id=? AND category='prep_offer'",
            (user_id, group_id)
        ).fetchone() is not None


def _has_juz_answer(user_id, group_id):
    with db() as c:
        return c.execute(
            "SELECT 1 FROM score_events WHERE student_id=? AND group_id=? AND category='prep_juz_answer'",
            (user_id, group_id)
        ).fetchone() is not None


def _get_juz_answer(user_id, group_id):
    with db() as c:
        row = c.execute(
            "SELECT subcategory, note FROM score_events WHERE student_id=? AND group_id=? AND category='prep_juz_answer'",
            (user_id, group_id)
        ).fetchone()
    return (row["subcategory"], int(row["note"])) if row else None


def _deactivate_from_prep(user_id, group_id):
    with db() as c:
        c.execute(
            "UPDATE user_groups SET active=0 WHERE user_id=? AND group_id=? AND role='student'",
            (user_id, group_id)
        )


def _deactivate_from_prep_by_group_id(phone, group_id):
    with db() as c:
        u = c.execute("SELECT id FROM users WHERE phone=?", (phone,)).fetchone()
        if u:
            c.execute(
                "UPDATE user_groups SET active=0 WHERE user_id=? AND group_id=? AND role='student'",
                (u["id"], group_id)
            )


def _group_lang(group_id):
    with db() as c:
        g = c.execute("SELECT lang FROM groups WHERE id=?", (group_id,)).fetchone()
        return (g["lang"] if g else None) or "ru"


def _group_title(group_id):
    with db() as c:
        g = c.execute("SELECT title FROM groups WHERE id=?", (group_id,)).fetchone()
        return (g["title"] if g else None) or ""
