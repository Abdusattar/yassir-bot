"""
Подтверждение реальности урока перед начислением баллов за "у"/"u".

Проблема: студент (а иногда и взрослый) мог написать "у" без реального
урока и получить +5 баллов за присутствие. Теперь баллы не начисляются
сразу - при первой отметке за день создаётся attendance_confirm, устазу
уходит вопрос с кнопками Да/Нет. Пока решения нет - баллы всем, кто успел
отметиться в этот день, висят в подвешенном состоянии (записи в
attendance_confirm_students, не в score_events). "Да" -> баллы начисляются
всем сразу. "Нет" -> никому не начисляются + предупреждение в группу.
Если устаз молчит ATTENDANCE_ESCALATE_MINUTES минут - тот же вопрос уходит
супер-админам (проверка в core/scheduler.py, переживает рестарт бота, т.к.
таймер хранится в БД, а не в памяти процесса).
"""
import logging

from config import SUPER_ADMIN_IDS
from core.db import (
    get_attendance_confirm_by_id, get_attendance_confirm_students,
    set_attendance_confirm_decision, get_stale_attendance_confirms,
    mark_attendance_confirm_escalated, add_bonus, get_group_by_id, get_group_admins,
)
from core.i18n import T, get_group_lang
from core.tg import send_message, send_message_with_buttons

log = logging.getLogger(__name__)

ATTENDANCE_ESCALATE_MINUTES = 30


def _names(students):
    return ", ".join(s["name"] for s in students)


async def ask_ustaz_attendance_confirm(confirm_id, group_id, lang):
    """Первая отметка "у" за день - спрашиваем всех админов группы в личке."""
    students = get_attendance_confirm_students(confirm_id)
    group = get_group_by_id(group_id)
    text = T("attendance_ask_ustaz", lang, group=group["title"] or "", names=_names(students))
    for admin_phone in get_group_admins(group_id):
        buttons = [
            (T("attendance_yes_btn", lang), f"att:yes:{admin_phone}:{confirm_id}"),
            (T("attendance_no_btn", lang), f"att:no:{admin_phone}:{confirm_id}"),
        ]
        await send_message_with_buttons(admin_phone, text, buttons)


async def resolve_attendance_confirm(confirm_id, decision):
    """decision: 'yes' | 'no'. Общая точка выхода и для устаза, и для
    супер-админа, и для случая "устаз сам отметил урок в группе"."""
    row = get_attendance_confirm_by_id(confirm_id)
    if not row or row["decision"] is not None:
        return False  # нет такой записи или уже решено (защита от повторного тапа)

    students = get_attendance_confirm_students(confirm_id)
    group = get_group_by_id(row["group_id"])
    lang = get_group_lang(group) if group else "ru"

    set_attendance_confirm_decision(confirm_id, decision)

    if decision == "yes":
        for s in students:
            add_bonus(s["id"], row["group_id"], row["date"], 5, "attendance", "online")
        if group and students:
            await send_message(group["chat_id"], T("attendance_confirmed_group", lang, names=_names(students)))
    else:
        if group and students:
            await send_message(group["chat_id"], T("attendance_denied_group", lang))

    log.info("Attendance confirm #%s (group=%s date=%s) resolved: %s",
              confirm_id, row["group_id"], row["date"], decision)
    return True


async def handle_attendance_confirm_answer(phone, choice, confirm_id):
    """Колбэк кнопки Да/Нет (от устаза или от супер-админа при эскалации)."""
    await resolve_attendance_confirm(confirm_id, choice)


async def check_attendance_confirm_escalations():
    """Вызывается из scheduler() каждые ~30 секунд. Если устаз не ответил
    за ATTENDANCE_ESCALATE_MINUTES - тот же вопрос уходит супер-админам."""
    for row in get_stale_attendance_confirms(ATTENDANCE_ESCALATE_MINUTES):
        mark_attendance_confirm_escalated(row["id"])
        students = get_attendance_confirm_students(row["id"])
        group = get_group_by_id(row["group_id"])
        if not group or not students:
            continue
        lang = get_group_lang(group)
        text = T("attendance_ask_superadmin", lang, group=group["title"] or "", names=_names(students))
        for admin_id in SUPER_ADMIN_IDS:
            buttons = [
                (T("attendance_yes_btn", lang), f"att:yes:{admin_id}:{row['id']}"),
                (T("attendance_no_btn", lang), f"att:no:{admin_id}:{row['id']}"),
            ]
            await send_message_with_buttons(admin_id, text, buttons)
        log.info("Attendance confirm #%s (group=%s date=%s) escalated to super admins",
                  row["id"], row["group_id"], row["date"])
