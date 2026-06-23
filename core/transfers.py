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
    get_skip_count_month, get_miss_count_last_30_days,
    deactivate_student, add_student, log_transfer, get_group,
    get_tadabbur_group
)
from core.i18n import T, get_group_lang
from core.tg import send_message
from config import SUPER_ADMIN_IDS

log = logging.getLogger(__name__)

# Пороговые дни бездействия
PRO_INACTIVE_DAYS = 14
RELAXED_INACTIVE_DAYS = 30
UPGRADE_MAX_MISSES = 3   # ≤3 пропуска за 30 дней → кандидат на повышение


async def run_transfer_checks():
    """Вызывается планировщиком ежедневно. Проверяет все группы."""
    groups = get_all_groups()
    for group in groups:
        gtype = group["group_type"] or "relaxed"
        if gtype == "tadabbur":
            continue
        await _check_group_for_transfers(group, gtype)


async def _check_group_for_transfers(group, gtype):
    chat_id = group["chat_id"]
    fallback_id = group["fallback_chat_id"]
    lang = get_group_lang(group)

    for student in get_students(group["id"]):
        if not student["phone"]:
            continue
        try:
            days_absent = get_days_since_last_report(student["id"])
            month_skips = get_skip_count_month(student["id"])

            if gtype == "pro" and month_skips >= PRO_INACTIVE_DAYS:
                await _transfer_to_tadabbur(student, group, fallback_id, month_skips, lang)

            elif gtype == "relaxed":
                if days_absent >= RELAXED_INACTIVE_DAYS:
                    await _transfer_to_tadabbur(student, group, fallback_id, days_absent, lang)
                elif _qualifies_for_upgrade(student["id"]):
                    await _suggest_upgrade(student, group, lang)

        except Exception as e:
            log.error("Transfer check error for student %s: %s", student["id"], e)


async def _transfer_to_tadabbur(student, group, fallback_id, days_absent, lang):
    chat_id = group["chat_id"]
    name = student["name"]
    sid = student["id"]

    # Деактивируем студента в текущей группе
    deactivate_student(sid, group["id"])

    # Целевая группа: явный fallback → иначе единственная tadabbur-группа профиля
    target_group = None
    if fallback_id:
        target_group = get_group(fallback_id)
    if not target_group:
        target_group = get_tadabbur_group()

    target_chat_id = target_group["chat_id"] if target_group else chat_id
    if target_group:
        add_student(name, target_group["id"], student["phone"])

    log_transfer(sid, chat_id, target_chat_id, f"inactive_{group['group_type']}")

    # Уведомляем студента
    msg = T("transfer_to_tadabbur", lang, name=name, days=days_absent)
    await send_message(chat_id, msg)

    # Уведомляем всех глобальных админов
    reason_label = "pro" if group["group_type"] == "pro" else "relaxed"
    admin_msg = T(
        "transfer_notify_admin", "ru",
        name=name, reason=reason_label, days=days_absent
    )
    for admin_id in SUPER_ADMIN_IDS:
        await send_message(admin_id, admin_msg)

    log.info("Student %s transferred from %s to tadabbur (%d days absent)", name, chat_id, days_absent)


def _qualifies_for_upgrade(sid):
    misses = get_miss_count_last_30_days(sid)
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
