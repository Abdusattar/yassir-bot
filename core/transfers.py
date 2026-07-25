"""
Логика переводов студентов между группами.

Схема переходов:
  pro  → (14 дней без отчёта)              → tadabbur
  relaxed → (30 дней без отчёта)           → tadabbur
  tadabbur/prep → (только через выпуск из prep) → relaxed
  relaxed → (≤3 пропуска за 30 дней, раз в 30 дней) → DM с кнопками "остаюсь"/
            "хочу в pro" (25.07.2026, см. _check_upgrade). Кто ещё не жал
            /start боту - вместо личного сообщения зовём в группе со ссылкой
            на старт (24ч на клик, дальше handle_dm_unlocked). Кик из
            relaxed — только по факту реального вступления в pro-группу
            (см. handle_known_user_group_join), не сразу после выбора.
"""
import logging
import asyncio
from datetime import datetime

from core.db import (
    get_all_groups, get_students, get_days_since_last_report,
    get_skip_count_month, get_skip_count_month_detail, get_miss_count_last_30_days,
    get_lesson_skip_count_month,
    deactivate_student, add_student, log_transfer, get_group, get_group_by_id,
    get_tadabbur_group, get_prep_group, get_overdue_unregistered, remove_unregistered,
    find_by_phone, find_user_by_phone, get_learning_group, is_any_group_admin,
    is_pending_prep_return, prep_days_done, mark_pending_prep_return,
    get_dm_ok_by_phone, get_best_pro_group_for_upgrade, create_upgrade_offer,
    delete_upgrade_offer, get_last_upgrade_offer_at, get_upgrade_offer_by_id,
    set_upgrade_decision, get_pending_upgrade_target, resolve_upgrade_offer,
    get_pending_group_nudge,
)
from core.prep import PREP_MIN_DAYS, announce_prep_graduate_arrival
from config import SUPER_ADMIN_IDS, IS_FEMALE, REQUIRE_PREP_FOR_NEW_STUDENTS
from core.i18n import T, get_group_lang
from core.tg import send_message, send_message_with_buttons, ban_member, unban_member, get_dm_start_link

log = logging.getLogger(__name__)

# Пороговые дни бездействия
PRO_INACTIVE_DAYS = 10
RELAXED_INACTIVE_DAYS = 20
UPGRADE_MAX_MISSES = 3      # ≤3 пропуска за 30 дней → кандидат на повышение в pro
UPGRADE_COOLDOWN_DAYS = 30  # раньше повторно не предлагаем, даже если снова подошёл
UPGRADE_OFFER_TTL_HOURS = 24  # сколько действует предложение с кнопками
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
                else:
                    await _check_upgrade(student, group, lang)

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


def _hours_since(ts):
    try:
        dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return 1e9
    return (datetime.utcnow() - dt).total_seconds() / 3600


async def _check_upgrade(student, group, lang):
    """Раз в UPGRADE_COOLDOWN_DAYS дней предлагаем relaxed-студенту, который
    почти не пропускает (≤UPGRADE_MAX_MISSES за 30 дней), перейти в pro
    (25.07.2026, решение пользователя). Кто уже жал /start боту (dm_ok) —
    личное сообщение с кнопками. Кто ещё не жал — сообщение в саму группу
    с упоминанием и ссылкой на старт бота (иначе личка недоступна, Telegram
    не даёт боту писать первым); если нажмёт старт в течение 24 часов,
    handle_dm_unlocked запустит настоящее DM-предложение. Якорь 30-дневного
    окна ставится в обоих случаях сразу, независимо от исхода."""
    sid = student["id"]
    phone = student["phone"]
    group_id = group["id"]
    name = student["name"]

    last_offer_at = get_last_upgrade_offer_at(sid, group_id)
    if last_offer_at and _hours_since(last_offer_at) < UPGRADE_COOLDOWN_DAYS * 24:
        return

    if get_miss_count_last_30_days(sid, group_id) > UPGRADE_MAX_MISSES:
        return

    # Нет ни одной pro-группы с местом — предложение бессмысленно, не шлём.
    if not get_best_pro_group_for_upgrade(lang):
        return

    if get_dm_ok_by_phone(phone):
        await _send_upgrade_dm(sid, phone, name, group_id, lang)
    else:
        await _send_upgrade_group_nudge(sid, phone, name, group, lang)


async def _send_upgrade_dm(sid, phone, name, group_id, lang):
    """Личное предложение с кнопками. Запись создаётся СРАЗУ, чтобы offer_id
    можно было вшить в callback_data кнопок (иначе тап по устаревшему
    сообщению резолвил бы не то предложение) - но если реальная отправка не
    удалась, откатываем, иначе якорь 30-дневного окна сдвинется без
    доставки (тот же класс бага, что и в core/prep.py)."""
    offer_id = create_upgrade_offer(sid, group_id, channel="dm")
    text = T("upgrade_offer_dm", lang, name=name)
    buttons = [
        (T("upgrade_stay_btn", lang), f"upg:stay:{phone}:{offer_id}"),
        (T("upgrade_pro_btn", lang), f"upg:pro:{phone}:{offer_id}"),
    ]
    resp = await send_message_with_buttons(phone, text, buttons)
    if resp and resp.get("ok"):
        log.info("Upgrade offer sent to %s (group=%s)", name, group_id)
    else:
        delete_upgrade_offer(offer_id)
        log.warning("Upgrade offer DM failed for %s (group=%s): %s", name, group_id, resp)


async def _send_upgrade_group_nudge(sid, phone, name, group, lang):
    """Студент ещё не жал /start - зовём его в группе, ссылкой на старт.
    Та же логика отката при неудачной отправке, что и у DM-варианта."""
    link = await get_dm_start_link()
    if not link:
        log.warning("Upgrade nudge: no start link (getMe failed), skip for %s", name)
        return
    offer_id = create_upgrade_offer(sid, group["id"], channel="group_nudge")
    text = T("upgrade_nudge_group", lang, name=name, link=link)
    resp = await send_message(group["chat_id"], text)
    if resp and resp.get("ok"):
        log.info("Upgrade nudge sent in group for %s (not dm_ok)", name)
    else:
        delete_upgrade_offer(offer_id)
        log.warning("Upgrade nudge failed for %s (group=%s): %s", name, group["id"], resp)


async def handle_dm_unlocked(phone):
    """Студент только что впервые открыл личку с ботом (mark_dm_ok_by_phone
    в handlers.py). Если у него есть непросроченный group_nudge (предложение
    relaxed→pro ушло в группу, т.к. личка была недоступна) - запускаем
    настоящее DM-предложение прямо сейчас, со свежими 24 часами на выбор
    кнопки (25.07.2026)."""
    row = get_pending_group_nudge(phone)
    if not row:
        return

    if _hours_since(row["offered_at"]) >= UPGRADE_OFFER_TTL_HOURS:
        set_upgrade_decision(row["id"], "expired")
        log.info("Upgrade group nudge expired before start for phone=%s", phone)
        return

    set_upgrade_decision(row["id"], "started")

    group = get_group_by_id(row["group_id"])
    user = find_user_by_phone(phone)
    if not group or not user:
        return
    lang = get_group_lang(group)
    await _send_upgrade_dm(row["student_id"], phone, user["name"], row["group_id"], lang)


async def handle_upgrade_answer(phone, choice, offer_id):
    """Колбэк кнопки под предложением relaxed→pro. choice: 'stay' | 'pro'."""
    row = get_upgrade_offer_by_id(offer_id)
    if not row or row["decision"] is not None:
        return  # нет такого предложения или уже отвечали (защита от двойного тапа)

    group = get_group_by_id(row["group_id"])
    lang = get_group_lang(group) if group else "ru"
    user = find_user_by_phone(phone)
    name = user["name"] if user else ""

    if _hours_since(row["offered_at"]) >= UPGRADE_OFFER_TTL_HOURS:
        set_upgrade_decision(row["id"], "expired")
        await send_message(phone, T("upgrade_expired", lang))
        log.info("Upgrade offer expired for %s", name)
        return

    if choice == "stay":
        set_upgrade_decision(row["id"], "stay")
        await send_message(phone, T("upgrade_stay_reply", lang, name=name))
        log.info("Upgrade offer: %s chose to stay", name)
        return

    # choice == "pro" — пересчитываем доступную группу заново (место могли
    # занять между отправкой предложения и нажатием кнопки).
    target = get_best_pro_group_for_upgrade(lang)
    if not target:
        set_upgrade_decision(row["id"], "pro_no_room")
        await send_message(phone, T("upgrade_pro_no_room", lang, name=name))
        log.info("Upgrade offer: %s wanted pro, no room left", name)
        return

    set_upgrade_decision(row["id"], "pro", target_group_id=target["id"])
    await send_message(phone, T("upgrade_pro_reply", lang, name=name, link=target["invite_link"]))
    log.info("Upgrade offer: %s chose pro, sent link to %s", name, target["title"])


async def handle_known_user_group_join(chat_id, group_info, uid, existing_user):
    """Общая логика для уже известного пользователя, вступившего в группу по
    приглашению (chat_member update) или добавленного вручную (new_chat_members).
    По приоритету:
      1) Уже активен в другой pro/relaxed группе — если это подтверждённый
         переход по предложению upgrade (см. handle_upgrade_answer) и целевая
         группа совпадает с этой — завершаем перевод; иначе просто игнор.
      2) pending_prep_return — блокируем до официального выпуска из prep.
      3) Обычная авторегистрация + возможный выпуск из подготовительной."""
    existing_group = get_learning_group(uid)
    gtype = group_info["group_type"] or "relaxed"

    if existing_group and gtype != "tadabbur":
        pending = get_pending_upgrade_target(uid)
        if pending and pending[1] == group_info["id"]:
            offer_id, _ = pending
            await _finalize_upgrade_arrival(offer_id, existing_user, existing_group, group_info, uid)
        else:
            log.info("join: %s already in another group, skip", uid)
        return

    if await block_return_if_pending_prep(existing_user["id"], existing_user["name"], uid, chat_id, group_info):
        return

    add_student(existing_user["name"], group_info["id"], uid)
    log.info("join: added existing user %s to group %s", existing_user["name"], group_info["id"])
    await announce_prep_graduate_arrival(chat_id, group_info["id"], uid)


async def _finalize_upgrade_arrival(offer_id, existing_user, old_group, new_group, phone):
    """Студент реально вступил в предложенную pro-группу — теперь и только
    теперь деактивируем и физически кикаем его из старой relaxed-группы
    (решение пользователя 25.07.2026: не раньше, чтобы не остаться без
    группы, если студент так и не перейдёт по ссылке). Плюс короткое
    представление-поздравление в новую группу (решение пользователя 25.07.2026)."""
    name = existing_user["name"]
    deactivate_student(existing_user["id"], old_group["id"])
    try:
        await ban_member(old_group["chat_id"], phone)
        await unban_member(old_group["chat_id"], phone)
    except Exception as e:
        log.error("Upgrade kick from relaxed failed for %s in %s: %s", name, old_group["chat_id"], e)
    add_student(name, new_group["id"], phone)
    resolve_upgrade_offer(offer_id)

    try:
        await send_message(new_group["chat_id"], T("upgrade_arrival_announce", get_group_lang(new_group), name=name))
    except Exception as e:
        log.warning("Upgrade arrival announce failed for %s in %s: %s", name, new_group["chat_id"], e)

    # В старую группу — как пример для остальных (решение пользователя 25.07.2026)
    try:
        await send_message(old_group["chat_id"], T("upgrade_departure_announce", get_group_lang(old_group), name=name))
    except Exception as e:
        log.warning("Upgrade departure announce failed for %s in %s: %s", name, old_group["chat_id"], e)

    log.info("Upgrade confirmed: %s moved from group %s to %s", name, old_group["id"], new_group["id"])


# ── Кик незарегистрированных ──────────────────────────────────────────────────

UNREG_DAYS = 7  # общий порог (относится к prep/tadabbur-подобным случаям)

# Кто зашёл напрямую в pro/relaxed, минуя подготовительную, и за сутки не
# представился — кикаем быстрее общего порога и шлём ссылку именно на
# подготовительную, а не на Тадаббур (решение пользователя 25.07.2026,
# см. new_student_needs_prep_group в handlers.py — это тот же сценарий,
# только для тех, кто игнорирует напоминание и ничего не пишет дальше).
UNREG_DAYS_PREP_BYPASS = 1


async def kick_unregistered():
    """Кикает из групп тех, кто не зарегистрировался. Для pro/relaxed — через
    UNREG_DAYS_PREP_BYPASS дней (ссылка на подготовительную), для остальных —
    через UNREG_DAYS (ссылка на Тадаббур)."""
    from core.tg import ban_member, unban_member
    tadabbur = get_tadabbur_group()
    prep_group = get_prep_group()
    overdue = get_overdue_unregistered(min(UNREG_DAYS, UNREG_DAYS_PREP_BYPASS))
    for row in overdue:
        uid = row["user_id"]
        chat_id = row["chat_id"]
        elapsed = row["elapsed"] or 0
        group = get_group(chat_id)
        gtype = (group["group_type"] or "relaxed") if group else "relaxed"
        is_prep_bypass = REQUIRE_PREP_FOR_NEW_STUDENTS and gtype in ("pro", "relaxed")
        threshold = UNREG_DAYS_PREP_BYPASS if is_prep_bypass else UNREG_DAYS
        if elapsed < threshold:
            # Личный порог этого типа группы ещё не истёк — запись не трогаем,
            # дождёмся следующей ежедневной проверки.
            continue
        try:
            # Пропускаем тадаббур — там регистрация не нужна
            if gtype == "tadabbur":
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
                if is_prep_bypass and prep_group and prep_group["invite_link"]:
                    msg = (
                        "👋 Участник зашёл напрямую, минуя подготовительную, и не представился — "
                        "сейчас будет удалён из группы.\n"
                        + addr + ", регистрация начинается с подготовительной группы:\n"
                        "👉 " + prep_group["invite_link"]
                    )
                else:
                    msg = "👋 Участник не представился в течение " + str(threshold) + " дней и сейчас будет удалён из группы."
                    if tadabbur and tadabbur["invite_link"]:
                        msg += (
                            "\n" + addr + ", кто хочет присоединиться к общему пространству Корана — добро пожаловать в Тадаббур:\n"
                            "👉 " + tadabbur["invite_link"]
                        )
                await send_message(chat_id, msg)
                await asyncio.sleep(10)
            await ban_member(chat_id, uid)
            await unban_member(chat_id, uid)
            log.info("Kicked unregistered user %s from %s (gtype=%s, threshold=%d)", uid, chat_id, gtype, threshold)
        except Exception as e:
            log.error("kick_unregistered error user=%s chat=%s: %s", uid, chat_id, e)
        finally:
            remove_unregistered(uid, chat_id)
