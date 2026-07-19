"""
Логика переводов студентов между группами.

Схема переходов:
  pro  → (14 дней без отчёта)              → tadabbur
  relaxed → (30 дней без отчёта)           → tadabbur
  tadabbur → (по желанию студента)         → relaxed
  relaxed → (≤3 пропуска за 30 дней)       → предлагаем pro (устаз выбирает группу)
"""
import logging
import asyncio

from core.db import (
    get_all_groups, get_students, get_days_since_last_report,
    get_skip_count_month, get_miss_count_last_30_days, get_lesson_skip_count_month,
    deactivate_student, add_student, log_transfer, get_group,
    get_tadabbur_group, get_overdue_unregistered, remove_unregistered,
    find_by_phone, is_any_group_admin
)
from config import SUPER_ADMIN_IDS
from core.i18n import T, get_group_lang
from core.tg import send_message, ban_member, unban_member

log = logging.getLogger(__name__)

# Пороговые дни бездействия
PRO_INACTIVE_DAYS = 10
RELAXED_INACTIVE_DAYS = 20
UPGRADE_MAX_MISSES = 3      # ≤3 пропуска за 30 дней → кандидат на повышение
PRO_LESSON_MISS_LIMIT = 3   # 3+ пропуска онлайн урока в месяц → перевод в тадаббур


async def run_transfer_checks():
    """Вызывается планировщиком ежедневно. Проверяет все группы."""
    groups = get_all_groups()
    for group in groups:
        gtype = group["group_type"] or "relaxed"
        if gtype == "tadabbur":
            continue
        await _check_group_for_transfers(group, gtype)
    await kick_unregistered()


async def _check_group_for_transfers(group, gtype):
    chat_id = group["chat_id"]
    fallback_id = group["fallback_chat_id"]
    lang = get_group_lang(group)

    for student in get_students(group["id"]):
        if not student["phone"]:
            continue
        try:
            days_absent = get_days_since_last_report(student["id"], group["id"])
            month_skips = get_skip_count_month(student["id"], group["id"])

            if gtype == "pro":
                if month_skips >= PRO_INACTIVE_DAYS:
                    await _transfer_to_tadabbur(student, group, fallback_id, month_skips, lang)
                else:
                    lesson_misses = get_lesson_skip_count_month(student["id"], group["id"])
                    if lesson_misses >= PRO_LESSON_MISS_LIMIT:
                        await _transfer_to_tadabbur(student, group, fallback_id, lesson_misses, lang, reason="lessons")

            elif gtype == "relaxed":
                if month_skips >= RELAXED_INACTIVE_DAYS:
                    await _transfer_to_tadabbur(student, group, fallback_id, month_skips, lang)
                elif _qualifies_for_upgrade(student["id"], group["id"]):
                    await _suggest_upgrade(student, group, lang)

        except Exception as e:
            log.error("Transfer check error for student %s: %s", student["id"], e)


async def _transfer_to_tadabbur(student, group, fallback_id, count, lang, reason="inactive"):
    chat_id = group["chat_id"]
    name = student["name"]
    sid = student["id"]

    # Деактивируем студента в текущей группе
    deactivate_student(sid, group["id"])

    # Физически убираем из исходного чата — иначе студент остаётся его участником
    # и следующим же сообщением там может случайно снова стать активным студентом
    # (дыра авторегистрации в handlers.py). Мягкий кик (ban+unban) — не блокирует
    # навсегда, при желании сможет вернуться по инвайт-ссылке.
    try:
        await ban_member(chat_id, student["phone"])
        await unban_member(chat_id, student["phone"])
    except Exception as e:
        log.error("Kick after transfer failed for student %s in %s: %s", sid, chat_id, e)

    # Целевая группа: явный fallback → иначе единственная tadabbur-группа профиля
    target_group = None
    if fallback_id:
        target_group = get_group(fallback_id)
    if not target_group:
        target_group = get_tadabbur_group()

    target_chat_id = target_group["chat_id"] if target_group else chat_id
    if target_group:
        # Добавляем только если ещё не в тадаббуре
        already = find_by_phone(student["phone"], target_group["id"])
        if not already:
            add_student(name, target_group["id"], student["phone"])

    log_transfer(sid, chat_id, target_chat_id, f"{reason}_{group['group_type']}")

    # Уведомляем студента
    if reason == "lessons":
        msg = T("transfer_to_tadabbur_lessons", lang, name=name, misses=count)
    else:
        msg = T("transfer_to_tadabbur", lang, name=name, days=count)
    await send_message(chat_id, msg)

    # Уведомляем всех глобальных админов
    admin_msg = T(
        "transfer_notify_admin", "ru",
        name=name, reason=reason + "_" + group["group_type"], days=count
    )
    for admin_id in SUPER_ADMIN_IDS:
        await send_message(admin_id, admin_msg)

    log.info("Student %s transferred from %s to tadabbur (reason=%s, count=%d)", name, chat_id, reason, count)


def _qualifies_for_upgrade(sid, group_id):
    misses = get_miss_count_last_30_days(sid, group_id)
    return misses <= UPGRADE_MAX_MISSES


async def _suggest_upgrade(student, group, lang):
    name = student["name"]
    sid = student["id"]
    chat_id = group["chat_id"]

    # Студенту в группе
    msg = T("upgrade_suggestion", lang, name=name)
    await send_message(chat_id, msg)

    # Устазу — в личку (нужно подтверждение с выбором целевой группы)
    admin_msg = T(
        "upgrade_notify_admin", "ru",
        name=name, group=group["title"] or chat_id, sid=sid
    )
    for admin_id in SUPER_ADMIN_IDS:
        await send_message(admin_id, admin_msg)

    log.info("Upgrade suggested for student %s from group %s", name, chat_id)


# ── Кик незарегистрированных через 7 дней ────────────────────────────────────

TADABBUR_INVITE = "https://t.me/+8dP2yljXPtJmM2Ey"
UNREG_DAYS = 7


async def kick_unregistered():
    """Кикает из учебных групп тех, кто не зарегистрировался за 14 дней.
    Отправляет ссылку на тадаббур."""
    from core.tg import ban_member, unban_member
    overdue = get_overdue_unregistered(UNREG_DAYS)
    for row in overdue:
        uid = row["user_id"]
        chat_id = row["chat_id"]
        try:
            group = get_group(chat_id)
            # Пропускаем тадаббур — там регистрация не нужна
            if group and (group["group_type"] or "relaxed") == "tadabbur":
                remove_unregistered(uid, chat_id)
                continue
            # Если уже зарегистрировался — просто чистим запись
            if group and find_by_phone(uid, group["id"]):
                remove_unregistered(uid, chat_id)
                continue
            # Устазов и супер-админов не кикаем — они могут состоять в группе
            # без прохождения студенческой регистрации
            if str(uid) in SUPER_ADMIN_IDS or is_any_group_admin(str(uid)):
                remove_unregistered(uid, chat_id)
                continue
            # Сначала сообщение — чтобы студент успел прочитать, пока ещё в группе,
            # и только потом кик (ban + unban = мягкое удаление, может вернуться)
            if group:
                await send_message(
                    chat_id,
                    "👋 Участник не представился в течение " + str(UNREG_DAYS) + " дней и сейчас будет удалён из группы.\n"
                    "Братья, кто хочет присоединиться к общему пространству Корана — добро пожаловать в Тадаббур:\n"
                    "👉 " + TADABBUR_INVITE
                )
                await asyncio.sleep(10)
            await ban_member(chat_id, uid)
            await unban_member(chat_id, uid)
            log.info("Kicked unregistered user %s from %s", uid, chat_id)
        except Exception as e:
            log.error("kick_unregistered error user=%s chat=%s: %s", uid, chat_id, e)
        finally:
            remove_unregistered(uid, chat_id)
