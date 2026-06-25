"""
Логика подготовительной группы (group_type='prep').

14 дней с момента вступления:
  ≥5 дней с отчётами → поздравление + выбор relaxed-группы (ky/ru) → ссылка в личку
  <5 дней             → остаётся в Тадаббуре, деактивируется из prep
"""
import logging

from core.db import (
    db, get_prep_students_due, count_report_days_since,
    get_relaxed_groups_by_lang, get_group_tasks,
)
from core.i18n import T, get_group_lang
from core.tg import send_message, tg_call

log = logging.getLogger(__name__)

PREP_DAYS = 14
PREP_MIN_DAYS = 5

# Ожидающие выбора языка: {phone: {group_id, name, glang, joined_date}}
_pending_lang_choice: dict = {}


async def check_prep_students():
    """Вызывается ежедневно в 21:00 рядом с check_transfers."""
    students = get_prep_students_due()
    for s in students:
        uid = s["phone"]
        group_id = s["group_id"]
        joined = s["joined_date"]
        glang = _group_lang(group_id)

        days_done = count_report_days_since(s["id"], group_id, joined)

        if days_done >= PREP_MIN_DAYS:
            _pending_lang_choice[uid] = {
                "group_id": group_id,
                "name": s["name"],
                "glang": glang,
                "joined_date": joined,
            }
            await _send_choice(uid, s["name"], days_done, glang)
        else:
            _deactivate_from_prep(s["id"], group_id)
            await send_message(uid, T("prep_failed", glang, name=s["name"], days=days_done))

        log.info("prep check: student=%s days_done=%d min=%d", s["name"], days_done, PREP_MIN_DAYS)


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
            days_left = max(0, PREP_DAYS - elapsed)
            if days_done >= 1:
                active_names.append((s["name"], days_done, days_left))
            else:
                passive_names.append((s["name"], days_left))

        lines = []
        if active_names:
            if glang == "ky":
                lines.append("✅ Тапшырып жатышкандар — мыкты, улантыңыздар:")
            else:
                lines.append("✅ Сдают отчёты — так держать:")
            for name, done, left in active_names:
                if glang == "ky":
                    lines.append(f"  • {name} — {done} күн тапшырды, {left} күн калды")
                else:
                    lines.append(f"  • {name} — {done} дн. сдано, осталось {left} дн.")

        if passive_names:
            if lines:
                lines.append("")
            if glang == "ky":
                lines.append(f"⏳ Азырынча тапшырбагандар — даярдык мезгили кыска, ≥5 күн тапшыруу зарыл:")
            else:
                lines.append(f"⏳ Пока не сдавали — период короткий, нужно ≥5 дней для перехода:")
            for name, left in passive_names:
                if glang == "ky":
                    lines.append(f"  • {name} — {left} күн калды")
                else:
                    lines.append(f"  • {name} — осталось {left} дн.")

        if lines:
            try:
                await send_message(chat_id, "\n".join(lines))
            except Exception as e:
                log.warning("prep reminder group=%s error: %s", chat_id, e)


async def handle_prep_callback(callback_query):
    """
    Обрабатывает нажатие inline-кнопки выбора языка группы.
    data: 'prep_lang:ky' или 'prep_lang:ru'
    """
    cq_id = callback_query.get("id")
    data = callback_query.get("data", "")
    user = callback_query.get("from", {})
    uid = str(user.get("id", ""))

    if not data.startswith("prep_lang:"):
        return False

    lang_choice = data.split(":")[1]
    pending = _pending_lang_choice.get(uid)

    await tg_call("answerCallbackQuery", {"callback_query_id": cq_id})

    if not pending:
        return True

    glang = pending["glang"]
    name = pending["name"]
    group_id = pending["group_id"]

    groups = get_relaxed_groups_by_lang(lang_choice)
    if not groups:
        await send_message(uid, T("prep_no_group", glang))
        return True

    target = groups[0]
    _deactivate_from_prep_by_group_id(uid, group_id)
    del _pending_lang_choice[uid]

    await send_message(uid, T("prep_group_link", glang,
                              title=target["title"], link=target["invite_link"]))

    log.info("prep graduate: %s → group=%s (%s)", name, target["title"], lang_choice)
    return True


async def _send_choice(uid, name, days_done, glang):
    text = T("prep_congrats", glang, name=name, days=days_done)
    buttons = {
        "inline_keyboard": [[
            {"text": T("prep_link_ky", glang), "callback_data": "prep_lang:ky"},
            {"text": T("prep_link_ru", glang), "callback_data": "prep_lang:ru"},
        ]]
    }
    await tg_call("sendMessage", {
        "chat_id": uid,
        "text": text,
        "reply_markup": buttons,
    })


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
