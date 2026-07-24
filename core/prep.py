"""
Логика подготовительной группы (group_type='prep').

Проверка идёт ежедневно по каждому активному студенту prep:
  ≥5 дней с отчётами (в любой момент, не дожидаясь 14 дней) →
                        поздравление студенту в личку + объявление в саму
                        prep-группу (мотивация остальным) + уведомление
                        ОДНОМУ конкретному устазу (не всем супер-админам —
                        решение пользователя 23.07.2026: если видят
                        несколько человек, могут по ошибке распределить
                        одного студента сразу в две группы). Устаз сам
                        вручную решает, в какую постоянную группу определить,
                        и зовёт студента туда. Повторяется КАЖДУЮ проверку,
                        пока студента реально не переведут — без этого
                        уведомление легко потерять среди других сообщений.
                        Из prep деактивируется и физически кикается только
                        когда студент реально станет активным в pro/relaxed
                        группе (см. announce_prep_graduate_arrival — теперь
                        срабатывает по факту, а не по заранее выбранной
                        целевой группе).
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
)
from core.i18n import T, get_group_lang
from core.tg import send_message, ban_member, unban_member

log = logging.getLogger(__name__)

PREP_DAYS = 14
PREP_MIN_DAYS = 5
PREP_EXTENSION_DAYS = 5  # доп. дни к дедлайну, если студент сдал ≥1 отчёт

# Кому лично уходит уведомление о выпускнике подготовительной — один
# конкретный человек на профиль, не все супер-админы (решение 23.07.2026,
# см. докстринг модуля выше).
_PREP_GRADUATE_ADMIN_ID = "5342232498" if IS_FEMALE else "7666229019"  # Зейнеб / Умар устаз


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
            already_notified = _has_prep_offer(s["id"], group_id)
            if not already_notified:
                # Студенту и в группу — один раз, не спамим при повторных проверках
                add_bonus(s["id"], group_id, joined, 0, "prep_offer")
                await send_message(uid, T("prep_congrats", glang, name=s["name"], days=days_done))
                await send_message(s["chat_id"], T("prep_success_group", glang, name=s["name"], days=days_done))

            # Устазу (одному конкретному, не всем супер-админам) — повторяем
            # КАЖДУЮ проверку, пока студента реально не переведут, иначе
            # уведомление легко потерять среди других сообщений. Из prep
            # студент уходит сам — announce_prep_graduate_arrival сработает,
            # когда он реально станет активным в новой группе.
            admin_msg = T(
                "prep_graduate_notify_admin", "ru",
                name=s["name"], days=days_done, group=s["title"] or s["chat_id"]
            ) + _group_sizes_text()
            await send_message(_PREP_GRADUATE_ADMIN_ID, admin_msg)
            log.info("prep check: student=%s days_done=%d → admin reminded for manual placement", s["name"], days_done)
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
    """Студент, уже выполнивший условие prep и ожидающий ручного перевода,
    сам написал боту в личку — считаем это напоминанием, шлём то же
    уведомление устазу ещё раз (решение пользователя 23.07.2026).
    Возвращает (name, lang) если напоминание реально отправлено (студент
    действительно ожидает перевода), иначе None — вызывающий код сам решает,
    что ответить."""
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
    admin_msg = T(
        "prep_graduate_notify_admin", "ru",
        name=row["name"], days=days_done, group=row["title"] or row["chat_id"]
    ) + _group_sizes_text()
    await send_message(_PREP_GRADUATE_ADMIN_ID, "🔔 Напоминание от студента:\n" + admin_msg)
    log.info("prep graduate reminder: %s nudged admin", row["name"])
    return (row["name"], row["lang"] or "ru")


def _group_sizes_text():
    """Список постоянных групп с количеством студентов - чтобы устаз видел
    нагрузку групп и решал, куда определить выпускника (24.07.2026)."""
    rows = get_regular_group_sizes()
    if not rows:
        return ""
    lines = ["", "📊 Студентов в группах:"]
    for r in rows:
        lines.append(f"  • {r['title']} ({r['group_type']}): {r['cnt']}")
    return "\n".join(lines)


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
