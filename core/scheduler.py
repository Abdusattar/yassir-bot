import asyncio
import logging
from datetime import datetime, timedelta

import pytz

from config import TZ, SUPER_ADMIN_IDS
from core.db import (
    get_all_groups, get_group_tasks, get_group_lang,
    get_students, get_today_report, get_consecutive_skips, get_skip_count_month,
    format_daily_report, format_period_report, get_period_winner,
    get_missing_students, get_date, get_tadabbur_group, get_students_not_in_tadabbur,
    get_setting, add_student, get_streak_days, add_bonus, db,
    get_days_since_last_report
)
from core.tg import send_message, tg_call
from core.i18n import T
from core.transfers import run_transfer_checks
from core.prep import check_prep_students, send_prep_reminders
import random
import core.ai as ai
import core.sampler as sampler

log = logging.getLogger(__name__)


def _now():
    return datetime.now(pytz.timezone(TZ))


# ── Утреннее напоминание (07:00) ──────────────────────────────────────────────

async def morning_reminder():
    hadith_pro     = sampler.sample_hadith()
    ayah_pro       = sampler.sample_ayah()
    hadith_relaxed = sampler.sample_hadith()
    ayah_relaxed   = sampler.sample_ayah()

    base_cache: dict = {}  # (gtype, lang) -> base_text

    for group in get_all_groups():
        gtype = group["group_type"] or "relaxed"
        if gtype == "tadabbur":
            continue
        chat_id = group["chat_id"]
        group_tasks = get_group_tasks(group)
        glang = get_group_lang(group)
        hadith = hadith_pro if gtype == "pro" else hadith_relaxed
        ayah   = ayah_pro   if gtype == "pro" else ayah_relaxed
        try:
            missing = get_missing_students(group["id"], group_tasks)
            if not missing:
                continue
            missing_names = [s["name"] for s, _ in missing]

            cache_key = (gtype, glang)
            if cache_key not in base_cache:
                base = await ai.group_motivation_base(glang, gtype, hadith=hadith, ayah=ayah)
                base_cache[cache_key] = base or ""
            base = base_cache[cache_key]

            if base and len(base) >= 30:
                names_str = ", ".join(missing_names)
                closing = ai.SUBMIT_TODAY.get(glang, ai.SUBMIT_TODAY["ru"])
                msg = base + "\n\n" + names_str + " " + closing
                await send_message(chat_id, "☀️ " + msg)
            await asyncio.sleep(1)
        except Exception as e:
            log.error("morning_reminder error in %s: %s", chat_id, e)


# ── Утренний отчёт в Тадаббур (07:00) — итоги вчера по всем группам ──────────

async def morning_tadabbur_report():
    tadabbur = get_tadabbur_group()
    if not tadabbur:
        return
    yesterday = (datetime.now(pytz.timezone(TZ)) - timedelta(days=1)).strftime("%Y-%m-%d")
    for group in get_all_groups():
        gtype = group["group_type"] or "relaxed"
        if gtype == "tadabbur":
            continue
        try:
            group_tasks = get_group_tasks(group)
            glang = get_group_lang(group)

            # Отчёт только по сдавшим — в ТДБР
            report = format_daily_report(
                group["id"], group["title"] or group["chat_id"],
                group_tasks, yesterday, submitted_only=True
            )
            label = "про-группы" if gtype == "pro" else "группы"
            msg = "📋 Итоги вчера — " + label + " " + (group["title"] or str(group["chat_id"])) + ":\n\n" + report
            await send_message(tadabbur["chat_id"], msg)
            await asyncio.sleep(1)

            # Личная насыха несдавшим вчера — один текст на всех
            missing = get_missing_students(group["id"], group_tasks, date=yesterday)
            phones = [s["phone"] for s, _ in missing if s.get("phone")]
            if phones:
                if random.random() < 0.5:
                    hadith, ayah = sampler.sample_hadith(), None
                else:
                    hadith, ayah = None, sampler.sample_ayah()
                msg_personal = await ai.morning_miss_nasiha(glang, hadith=hadith, ayah=ayah)
                if msg_personal and len(msg_personal) >= 20:
                    for phone in phones:
                        try:
                            await send_message(phone, "🤲 " + msg_personal)
                        except Exception:
                            pass
                        await asyncio.sleep(0.5)
        except Exception as e:
            log.error("morning_tadabbur_report error in %s: %s", group["chat_id"], e)


# ── Бонус +5 за 7 дней стрика (07:00) ────────────────────────────────────────

async def streak_bonuses():
    hadith = sampler.sample_hadith()
    ayah   = sampler.sample_ayah()
    today = get_date()
    for group in get_all_groups():
        gtype = group["group_type"] or "relaxed"
        if gtype == "tadabbur":
            continue
        glang = get_group_lang(group)
        try:
            bonus_names = []
            for s in get_students(group["id"]):
                streak = get_streak_days(s["id"])
                if streak > 0 and streak % 7 == 0:
                    subcat = "week_" + str(streak // 7)
                    with db() as c:
                        exists = c.execute(
                            "SELECT 1 FROM score_events"
                            " WHERE student_id=? AND category='streak' AND subcategory=?",
                            (s["id"], subcat)
                        ).fetchone()
                    if not exists:
                        add_bonus(s["id"], group["id"], today, 5, "streak", subcat)
                        bonus_names.append((s["name"], streak))
                    # AI-похвала на ключевых рубежах
                    if streak in (7, 14, 30):
                        praise = await ai.personal_streak_praise(s["name"], streak, glang, hadith=hadith, ayah=ayah)
                        if praise:
                            await send_message(group["chat_id"], "🌟 " + praise)
                        await asyncio.sleep(1)
            if bonus_names:
                lines = ["🌟 Бонус +5 очков за серию без пропусков:"]
                for name, days in bonus_names:
                    lines.append("• " + name + " — " + str(days) + " дней подряд!")
                await send_message(group["chat_id"], "\n".join(lines))
            await asyncio.sleep(1)
        except Exception as e:
            log.error("streak_bonuses error in %s: %s", group["chat_id"], e)


# ── Личные напоминания (18:00) ─────────────────────────────────────────────────

async def individual_reminders():
    """15:00 — личное сообщение братьям/сёстрам, пропустившим 3+ дней. Только в личку."""
    hadith_pro     = sampler.sample_hadith()
    ayah_pro       = sampler.sample_ayah()
    hadith_relaxed = sampler.sample_hadith()
    ayah_relaxed   = sampler.sample_ayah()

    for group in get_all_groups():
        gtype = group["group_type"] or "relaxed"
        if gtype == "tadabbur":
            continue
        glang = get_group_lang(group)
        hadith = hadith_pro if gtype == "pro" else hadith_relaxed
        ayah   = ayah_pro   if gtype == "pro" else ayah_relaxed
        try:
            for s in get_students(group["id"]):
                if not s.get("phone"):
                    continue
                missed = get_days_since_last_report(s["id"])
                if missed >= 3:
                    msg = await ai.absent_motivation(s["name"], missed, glang, hadith=hadith, ayah=ayah)
                    if msg and len(msg) >= 30:
                        try:
                            await send_message(s["phone"], "🤲 " + msg)
                        except Exception:
                            pass
                    await asyncio.sleep(1)
        except Exception as e:
            log.error("individual_reminders error in %s: %s", group["chat_id"], e)


async def personal_reminders():
    """18:00 — групповой призыв несдавшим сегодня."""
    hadith_pro     = sampler.sample_hadith()
    ayah_pro       = sampler.sample_ayah()
    hadith_relaxed = sampler.sample_hadith()
    ayah_relaxed   = sampler.sample_ayah()

    base_cache: dict = {}  # (gtype, lang) -> base_text

    for group in get_all_groups():
        gtype = group["group_type"] or "relaxed"
        if gtype == "tadabbur":
            continue
        group_tasks = get_group_tasks(group)
        glang = get_group_lang(group)
        chat_id = group["chat_id"]
        hadith = hadith_pro if gtype == "pro" else hadith_relaxed
        ayah   = ayah_pro   if gtype == "pro" else ayah_relaxed
        try:
            missing = get_missing_students(group["id"], group_tasks)
            if not missing:
                continue
            missing_names = [s["name"] for s, _ in missing]

            cache_key = (gtype, glang)
            if cache_key not in base_cache:
                base = await ai.group_motivation_base(glang, gtype, hadith=hadith, ayah=ayah)
                base_cache[cache_key] = base or ""
            base = base_cache[cache_key]

            if base and len(base) >= 30:
                names_str = ", ".join(missing_names)
                closing = ai.SUBMIT_TODAY.get(glang, ai.SUBMIT_TODAY["ru"])
                msg = base + "\n\n" + names_str + " " + closing
                await send_message(chat_id, "📖 " + msg)
            await asyncio.sleep(1)
        except Exception as e:
            log.error("personal_reminders error in %s: %s", chat_id, e)


# ── Вечерний отчёт (20:00) ────────────────────────────────────────────────────

async def evening_report():
    hadith = sampler.sample_hadith()
    ayah   = sampler.sample_ayah()
    today = get_date()
    for group in get_all_groups():
        gtype = group["group_type"] or "relaxed"
        if gtype == "tadabbur":
            continue
        chat_id = group["chat_id"]
        group_tasks = get_group_tasks(group)
        glang = get_group_lang(group)
        try:
            report_text = format_daily_report(group["id"], group["title"] or chat_id, group_tasks, today)
            await send_message(chat_id, report_text)

            students = get_students(group["id"])
            full_done = [
                s for s in students
                if (rep := get_today_report(s["id"], group["id"])) and all(rep[k] for k in group_tasks)
            ]
            if full_done:
                names = [s["name"] for s in full_done]
                praise = await ai.group_praise(names, glang, hadith=hadith, ayah=ayah)
                if praise:
                    await send_message(chat_id, "🌟 " + praise)
            await asyncio.sleep(1)
        except Exception as e:
            log.error("evening_report error in %s: %s", chat_id, e)


# ── Предупреждение о пропусках (20:30) ───────────────────────────────────────

async def skip_warnings():
    hadith = sampler.sample_hadith()
    ayah   = sampler.sample_ayah()
    for group in get_all_groups():
        gtype = group["group_type"] or "relaxed"
        if gtype == "tadabbur":
            continue
        glang = get_group_lang(group)
        chat_id = group["chat_id"]
        try:
            for s in get_students(group["id"]):
                if not s["phone"]:
                    continue
                if gtype == "pro":
                    skips = get_skip_count_month(s["id"])
                    warn_threshold = 5
                    transfer_limit = 10
                else:
                    skips = get_skip_count_month(s["id"])
                    warn_threshold = 15
                    transfer_limit = 20
                if skips >= warn_threshold:
                    warn = await ai.warning_skips(s["name"], skips, transfer_limit, glang, hadith=hadith, ayah=ayah)
                    if warn:
                        await send_message(s["phone"], "⚠️ " + warn)
                    await asyncio.sleep(0.8)
        except Exception as e:
            log.error("skip_warnings error in %s: %s", chat_id, e)


# ── Тадаббур-пост (14:00) ─────────────────────────────────────────────────────

async def tadabbur_post():
    tadabbur = get_tadabbur_group()
    if not tadabbur:
        return
    try:
        text = await ai.daily_tadabbur_post()
        if text and len(text) >= 50:
            await send_message(tadabbur["chat_id"], text)
    except Exception as e:
        log.error("tadabbur_post error: %s", e)


# ── Ежедневная насыха в Тадаббур (09:00) ─────────────────────────────────────

async def tadabbur_nasiha():
    tadabbur = get_tadabbur_group()
    if not tadabbur:
        return
    hadith = sampler.sample_hadith()
    ayah   = sampler.sample_ayah()
    try:
        text = await ai.group_motivation_base("ru", "relaxed", hadith=hadith, ayah=ayah, model="deepseek/deepseek-v4-pro")
        if text and len(text) >= 50:
            await send_message(tadabbur["chat_id"], "📖\n\n" + text)
    except Exception as e:
        log.error("tadabbur_nasiha error: %s", e)


# ── Приглашение в Тадаббур (10:00) ───────────────────────────────────────────

TADABBUR_INVITE = "https://t.me/+8dP2yljXPtJmM2Ey"

async def _sync_tadabbur_member(student, tadabbur):
    """Проверяет через Telegram API — реально ли студент в Тадаббур-группе.
    Если да — добавляет в user_groups и возвращает True."""
    phone = student["phone"]
    if not phone:
        return False
    try:
        resp = await tg_call("getChatMember", {
            "chat_id": int(tadabbur["chat_id"]),
            "user_id": int(phone)
        })
        status = (resp or {}).get("result", {}).get("status", "")
        if status in ("member", "administrator", "creator"):
            add_student(student["name"], tadabbur["id"], phone)
            return True
    except Exception as e:
        log.debug("getChatMember error for %s: %s", phone, e)
    return False


async def tadabbur_invite_reminder():
    tadabbur = get_tadabbur_group()
    if not tadabbur:
        return
    for group in get_all_groups():
        if group["group_type"] == "tadabbur":
            continue
        try:
            missing = get_students_not_in_tadabbur(group["id"])
            if not missing:
                continue
            # Синхронизируем: кто уже вступил в Telegram — добавляем в БД
            truly_missing = []
            for s in missing:
                already_in = await _sync_tadabbur_member(s, tadabbur)
                if not already_in:
                    truly_missing.append(s)
            if not truly_missing:
                continue
            names = "\n".join("• " + s["name"] for s in truly_missing)
            msg = (
                "📚 Братья, напоминаем! Присоединяйтесь к нашей общей группе "
                "Тадаббур — пространство красоты и смыслов Корана, общих отчётов и объявлений 🌿\n\n"
                "Ещё не в группе:\n" + names + "\n\n"
                "👉 " + TADABBUR_INVITE
            )
            await send_message(group["chat_id"], msg)
        except Exception as e:
            log.error("tadabbur_invite_reminder error in %s: %s", group["chat_id"], e)


# ── Проверка переводов (21:00) ─────────────────────────────────────────────────

async def transfer_check():
    try:
        await run_transfer_checks()
    except Exception as e:
        log.error("transfer_check error: %s", e)


# ── Еженедельный отчёт (воскресенье 19:00) ────────────────────────────────────

async def weekly_report():
    hadith = sampler.sample_hadith()
    ayah   = sampler.sample_ayah()
    for group in get_all_groups():
        if (group["group_type"] or "relaxed") == "tadabbur":
            continue
        chat_id = group["chat_id"]
        group_tasks = get_group_tasks(group)
        glang = get_group_lang(group)
        try:
            report = format_period_report(group["id"], group["title"] or chat_id, group_tasks, 7)
            await send_message(chat_id, report)

            winner = get_period_winner(group["id"], 7)
            if winner and winner["points"] > 0:
                praise = await ai.winner_praise(winner["name"], "неделю", winner["points"], glang, hadith=hadith, ayah=ayah)
                if praise:
                    await send_message(chat_id, praise)
            await asyncio.sleep(1)
        except Exception as e:
            log.error("weekly_report error in %s: %s", chat_id, e)


# ── Ежемесячный отчёт (1-е число 19:00) ──────────────────────────────────────

async def monthly_report():
    hadith = sampler.sample_hadith()
    ayah   = sampler.sample_ayah()
    for group in get_all_groups():
        if (group["group_type"] or "relaxed") == "tadabbur":
            continue
        chat_id = group["chat_id"]
        group_tasks = get_group_tasks(group)
        glang = get_group_lang(group)
        try:
            report = format_period_report(group["id"], group["title"] or chat_id, group_tasks, 30)
            await send_message(chat_id, report)

            winner = get_period_winner(group["id"], 30)
            if winner and winner["points"] > 0:
                praise = await ai.winner_praise(winner["name"], "месяц", winner["points"], glang, hadith=hadith, ayah=ayah)
                if praise:
                    await send_message(chat_id, praise)
            await asyncio.sleep(1)
        except Exception as e:
            log.error("monthly_report error in %s: %s", chat_id, e)

    # Устазу — общая сводка по всем группам
    try:
        if SUPER_ADMIN_IDS:
            lines = ["📊 Итог месяца — все группы:"]
            for g in get_all_groups():
                cnt = len(get_students(g["id"]))
                lines.append("• " + (g["title"] or g["chat_id"]) + ": " + str(cnt) + " студентов")
            lines.append("\nАль-хамду лиллях! 🤲")
            for admin_id in SUPER_ADMIN_IDS:
                await send_message(admin_id, "\n".join(lines))
    except Exception as e:
        log.error("monthly_report admin summary error: %s", e)


# ── Воскресенье 20:30 — Ясир спрашивает устаза ───────────────────────────────

async def yassir_asks_admin():
    try:
        question = await ai.ask_admin_improvement(get_all_groups())
        if question:
            for ap in SUPER_ADMIN_IDS:
                await send_message(ap,
                    "🤖 Ясир хочет стать лучше:\n\n" + question +
                    "\n\nОтветь: /teach твой ответ")
    except Exception as e:
        log.error("yassir_asks_admin error: %s", e)


# ── Годовой отчёт (1 января 11:00) ────────────────────────────────────────────

async def yearly_report():
    for group in get_all_groups():
        if (group["group_type"] or "relaxed") == "tadabbur":
            continue
        chat_id = group["chat_id"]
        group_tasks = get_group_tasks(group)
        try:
            report = format_period_report(group["id"], group["title"] or chat_id, group_tasks, 365)
            await send_message(chat_id, "🎊 ИТОГИ ГОДА! 🎊\n\n" + report)
            await asyncio.sleep(1)
        except Exception as e:
            log.error("yearly_report error in %s: %s", chat_id, e)


# ── Главный планировщик ────────────────────────────────────────────────────────

async def scheduler():
    """Бесконечный цикл планировщика. Запускается как asyncio Task из bot.py."""
    log.info("Scheduler started")
    await asyncio.sleep(10)

    fired_today: set = set()

    while True:
        try:
            now = _now()
            slot = (now.hour, now.minute, now.weekday(), now.day)

            async def maybe_run(label, coro_fn, *args):
                key = (label, slot[2], slot[3], now.date().isoformat())
                if key not in fired_today:
                    fired_today.add(key)
                    fired_today.discard(
                        (label, slot[2], slot[3],
                         (now.date() - timedelta(days=1)).isoformat())
                    )
                    log.info("Scheduler: %s", label)
                    await coro_fn(*args)

            h, m, wd, d = slot

            if h == 7 and m == 0:
                await maybe_run("morning_tadabbur_report", morning_tadabbur_report)
                await maybe_run("streak_bonuses", streak_bonuses)
                await maybe_run("tadabbur_invite_morning", tadabbur_invite_reminder)
                await maybe_run("prep_reminders", send_prep_reminders)
            elif h == 9 and m == 0:
                await maybe_run("tadabbur_nasiha", tadabbur_nasiha)
            elif h == 14 and m == 0:
                await maybe_run("tadabbur_post", tadabbur_post)
            elif h == 15 and m == 0:
                await maybe_run("individual_reminders", individual_reminders)
            elif h == 20 and m == 30:
                await maybe_run("skip_warnings", skip_warnings)
            elif h == 21 and m == 0:
                await maybe_run("transfer_check", transfer_check)
                await maybe_run("prep_check", check_prep_students)
            elif wd == 6 and h == 19 and m == 0:
                await maybe_run("weekly_report", weekly_report)
            elif wd == 6 and h == 20 and m == 30:
                await maybe_run("yassir_asks_admin", yassir_asks_admin)
            elif d == 1 and h == 19 and m == 0:
                await maybe_run("monthly_report", monthly_report)
            elif d == 1 and now.month == 1 and h == 11 and m == 0:
                await maybe_run("yearly_report", yearly_report)

            await asyncio.sleep(30)

        except Exception as e:
            log.error("Scheduler loop error: %s", e)
            await asyncio.sleep(60)
