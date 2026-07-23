"""
Логика переводов студентов между группами.

Схема переходов:
  pro  → (14 дней без отчёта)              → tadabbur
  relaxed → (30 дней без отчёта)           → tadabbur
  tadabbur/prep → (только через выпуск из prep) → relaxed
  relaxed → (≤3 пропуска за 30 дней)       → предлагаем pro (устаз выбирает группу)
"""
import logging
import asyncio
from datetime import datetime

from core.db import (
    get_all_groups, get_students, get_days_since_last_report,
    get_skip_count_month, get_skip_count_month_detail, get_miss_count_last_30_days,
    get_lesson_skip_count_month,
    deactivate_student, add_student, log_transfer, get_group,
    get_tadabbur_group, get_prep_group, get_overdue_unregistered, remove_unregistered,
    find_by_phone, is_any_group_admin, is_pending_prep_return, prep_days_done,
    mark_pending_prep_return
)
from core.prep import PREP_MIN_DAYS
from config import SUPER_ADMIN_IDS, IS_FEMALE
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
            detail = get_skip_count_month_detail(student["id"], group["id"])
            month_skips = detail["missed"] if detail else 0

            if gtype == "pro":
                if month_skips >= PRO_INACTIVE_DAYS:
                    await _transfer_to_tadabbur(student, group, fallback_id, month_skips, lang, detail=detail, threshold=PRO_INACTIVE_DAYS)
                else:
                    lesson_misses = get_lesson_skip_count_month(student["id"], group["id"])
                    if lesson_misses >= PRO_LESSON_MISS_LIMIT:
                        await _transfer_to_tadabbur(student, group, fallback_id, lesson_misses, lang, reason="lessons")

            elif gtype == "relaxed":
                if month_skips >= RELAXED_INACTIVE_DAYS:
                    await _transfer_to_tadabbur(student, group, fallback_id, month_skips, lang, detail=detail, threshold=RELAXED_INACTIVE_DAYS)
                elif _qualifies_for_upgrade(student["id"], group["id"]):
                    await _suggest_upgrade(student, group, lang)

        except Exception as e:
            log.error("Transfer check error for student %s: %s", student["id"], e)


def _fmt_dm(iso_date):
    """'2026-07-01' → '01.07'"""
    d = datetime.strptime(iso_date, "%Y-%m-%d").date()
    return "{:02d}.{:02d}".format(d.day, d.month)


async def _transfer_to_tadabbur(student, group, fallback_id, count, lang, reason="inactive", detail=None, threshold=None):
    chat_id = group["chat_id"]
    name = student["name"]
    sid = student["id"]

    # Деактивируем студента в текущей группе
    deactivate_student(sid, group["id"])

    # Маркер "кикнут за пропуски сдачи заданий, должен вернуться только
    # через официальный выпуск из prep" (решение пользователя 23.07.2026).
    # Только reason="inactive" — именно пропуски отчётов, не пропуски уроков.
    if reason == "inactive":
        mark_pending_prep_return(student["phone"], group["id"], reason)

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
    elif detail:
        msg = T("transfer_to_tadabbur", lang, name=name,
                 start=_fmt_dm(detail["start"]), end=_fmt_dm(detail["end"]),
                 submitted=detail["submitted"], total=detail["total"], threshold=threshold)
    else:
        msg = T("transfer_to_tadabbur", lang, name=name,
                 start="", end="", submitted=0, total=count, threshold=threshold or count)
    await send_message(chat_id, msg)

    # Уведомляем всех глобальных админов
    admin_msg = T(
        "transfer_notify_admin", "ru",
        name=name, reason=reason + "_" + group["group_type"], days=count,
        group=group["title"] or chat_id
    )
    for admin_id in SUPER_ADMIN_IDS:
        await send_message(admin_id, admin_msg)

    log.info("Student %s transferred from %s to tadabbur (reason=%s, count=%d)", name, chat_id, reason, count)


async def block_return_if_pending_prep(uid, name, phone, chat_id, group):
    """Закрывает дыру авторегистрации: студент, кикнутый за пропуски сдачи
    заданий и ещё не выпустившийся из prep официально (pending_prep_return),
    не может автоматически "воскреснуть" студентом в pro/relaxed напрямую —
    только через официальный выпуск из prep.

    Возвращает True, если студента заблокировали и кикнули (вызывающий код
    не должен добавлять его в группу). False — путь свободен, можно
    регистрировать как обычно."""
    gtype = group["group_type"] or "relaxed"
    if gtype not in ("pro", "relaxed"):
        return False
    if not is_pending_prep_return(phone):
        return False
    if prep_days_done(phone) >= PREP_MIN_DAYS:
        # Реально выполнил условие подготовительной (не просто состоит там)
        # — это и есть легитимный путь выпуска (см. core/prep.py
        # announce_prep_graduate_arrival, которая снимет pending_prep_return
        # сама). НЕ блокировать, иначе дедлок: маркер снимается только там,
        # а туда мы бы никогда не пустили. Тот же порог (PREP_MIN_DAYS),
        # что и announce — иначе можно проскочить с недобранными днями.
        return False

    lang = get_group_lang(group)

    try:
        await ban_member(chat_id, phone)
        await unban_member(chat_id, phone)
    except Exception as e:
        log.error("Kick (return without prep) failed for %s in %s: %s", uid, chat_id, e)

    prep_group = get_prep_group()
    prep_link = prep_group["invite_link"] if prep_group and prep_group["invite_link"] else ""

    # Сначала личка — от результата зависит, что написать в группу (иначе
    # группа может заявить "отправили в личку", хотя доставка не прошла,
    # например если студент ни разу не писал боту в личку напрямую).
    dm_resp = await send_message(phone, T("return_needs_prep_dm", lang, name=name, prep_link=prep_link))
    dm_ok = bool(dm_resp and dm_resp.get("ok"))

    if dm_ok:
        await send_message(chat_id, T("return_needs_prep_group", lang, name=name))
        admin_msg = T("return_blocked_notify_admin", "ru", name=name, group=group["title"] or chat_id)
    else:
        await send_message(chat_id, T("return_needs_prep_group_dm_failed", lang, name=name, prep_link=prep_link))
        admin_msg = T("return_blocked_notify_admin_dm_failed", "ru", name=name, group=group["title"] or chat_id)

    for admin_id in SUPER_ADMIN_IDS:
        await send_message(admin_id, admin_msg)

    log.info("Blocked return without prep: %s in %s", name, chat_id)
    return True


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

UNREG_DAYS = 7


async def kick_unregistered():
    """Кикает из учебных групп тех, кто не зарегистрировался за 14 дней.
    Отправляет ссылку на тадаббур."""
    from core.tg import ban_member, unban_member
    tadabbur = get_tadabbur_group()
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
                addr = "Сёстры" if IS_FEMALE else "Братья"
                msg = "👋 Участник не представился в течение " + str(UNREG_DAYS) + " дней и сейчас будет удалён из группы."
                if tadabbur and tadabbur["invite_link"]:
                    msg += (
                        "\n" + addr + ", кто хочет присоединиться к общему пространству Корана — добро пожаловать в Тадаббур:\n"
                        "👉 " + tadabbur["invite_link"]
                    )
                await send_message(chat_id, msg)
                await asyncio.sleep(10)
            await ban_member(chat_id, uid)
            await unban_member(chat_id, uid)
            log.info("Kicked unregistered user %s from %s", uid, chat_id)
        except Exception as e:
            log.error("kick_unregistered error user=%s chat=%s: %s", uid, chat_id, e)
        finally:
            remove_unregistered(uid, chat_id)
