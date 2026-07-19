"""
Логика подготовительной группы (group_type='prep').

Проверка идёт ежедневно по каждому активному студенту prep:
  ≥5 дней с отчётами (в любой момент, не дожидаясь 14 дней) →
                        поздравление + выбор relaxed-группы (ky/ru) → ссылка в личку.
                        Предложение отправляется один раз (метится add_bonus
                        category='prep_offer'), повторно не спамим.
                        Из prep деактивируется только когда студент подтверждённо
                        вступит в целевую группу (announce_prep_graduate_arrival) —
                        чтобы не потерять его, если ссылкой не воспользуется.
  <5 дней за 14 дней   → остаётся в Тадаббуре, деактивируется из prep
                        и физически кикается (мягко, ban+unban) из чата —
                        иначе дыра авторегистрации: следующим же сообщением
                        в этом чате студент молча вернётся активным (было
                        реальным инцидентом, см. wiki/prep_group.md).
"""
import logging

from core.db import (
    db, get_prep_students_active, count_report_days_since, add_bonus,
    get_relaxed_groups_by_lang, get_group_tasks,
    add_prep_graduate, pop_prep_graduate,
    get_tadabbur_group, add_student,
)
from core.i18n import T, get_group_lang
from core.tg import send_message, tg_call, ban_member, unban_member

log = logging.getLogger(__name__)

PREP_DAYS = 14
PREP_MIN_DAYS = 5

# Ожидающие выбора языка: {phone: {group_id, name, glang, joined_date}}
_pending_lang_choice: dict = {}


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
            if _has_prep_offer(s["id"], group_id):
                continue  # уже предлагали выбор группы, ждём решения студента
            add_bonus(s["id"], group_id, joined, 0, "prep_offer")
            _pending_lang_choice[uid] = {
                "group_id": group_id,
                "chat_id": s["chat_id"],
                "name": s["name"],
                "glang": glang,
                "joined_date": joined,
            }
            await _send_choice(uid, s["name"], days_done, glang)
            log.info("prep check: student=%s days_done=%d → offer sent (elapsed=%.1f)", s["name"], days_done, elapsed)
        elif elapsed >= PREP_DAYS:
            _deactivate_from_prep(s["id"], group_id)
            await send_message(uid, T("prep_failed", glang, name=s["name"], days=days_done))
            try:
                await ban_member(s["chat_id"], uid)
                await unban_member(s["chat_id"], uid)
            except Exception as e:
                log.error("prep fail kick error student=%s chat=%s: %s", s["name"], s["chat_id"], e)
            log.info("prep check: student=%s days_done=%d < %d after %d days → failed, kicked", s["name"], days_done, PREP_MIN_DAYS, PREP_DAYS)


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
    from_chat_id = pending["chat_id"]

    groups = get_relaxed_groups_by_lang(lang_choice)
    if not groups:
        await send_message(uid, T("prep_no_group", glang))
        return True

    target = groups[0]
    del _pending_lang_choice[uid]

    await send_message(uid, T("prep_group_link", glang,
                              title=target["title"], link=target["invite_link"]))

    # Из prep не убираем и никуда не объявляем прямо сейчас — только когда
    # студент реально вступит в целевую группу (см. announce_prep_graduate_arrival).
    # Так студент не потеряется, если ссылкой не воспользуется.
    add_prep_graduate(uid, target["id"], name, group_id, from_chat_id)

    # Страховка: сразу добавляем в Тадаббур на случай, если ссылкой на целевую
    # группу так и не воспользуется — чтобы не остаться совсем без группы.
    tadabbur = get_tadabbur_group()
    if tadabbur:
        add_student(name, tadabbur["id"], uid)

    log.info("prep graduate pending: %s → group=%s (%s), ждём подтверждения вступления", name, target["title"], lang_choice)
    return True


async def announce_prep_graduate_arrival(chat_id, group_id, phone):
    """Вызывается когда известный студент вступает в группу по инвайт-ссылке.
    Если это подтверждённый выпускник prep — деактивирует его в старой группе
    и объявляет о переходе в обоих чатах."""
    rec = pop_prep_graduate(phone, group_id)
    if not rec:
        return

    _deactivate_from_prep_by_group_id(phone, rec["from_group_id"])

    new_glang = _group_lang(group_id)
    old_glang = _group_lang(rec["from_group_id"])
    new_title = _group_title(group_id)

    try:
        await send_message(chat_id, T("prep_graduate_announce_new", new_glang, name=rec["name"]))
    except Exception as e:
        log.warning("prep graduate new-group announce failed: %s", e)

    try:
        await send_message(rec["from_chat_id"], T("prep_graduate_announce_old", old_glang, name=rec["name"], title=new_title))
    except Exception as e:
        log.warning("prep graduate old-group announce failed: %s", e)

    log.info("prep graduate confirmed: %s arrived in group=%s", rec["name"], group_id)


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


def _has_prep_offer(user_id, group_id):
    with db() as c:
        return c.execute(
            "SELECT 1 FROM score_events WHERE student_id=? AND group_id=? AND category='prep_offer'",
            (user_id, group_id)
        ).fetchone() is not None


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
