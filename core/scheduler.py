import asyncio
import logging
from datetime import datetime, timedelta

import pytz

from config import TZ, ADMIN_PHONES
from core.db import (
    get_all_groups, get_group_tasks, get_group_lang,
    get_students, get_today_report, get_consecutive_skips,
    format_daily_report, format_period_report, get_period_winner,
    get_missing_students, get_date
)
from core.tg import send_message
from core.i18n import T
from core.transfers import run_transfer_checks
import core.ai as ai

log = logging.getLogger(__name__)


def _now():
    return datetime.now(pytz.timezone(TZ))


# ── Утреннее напоминание (07:00) ──────────────────────────────────────────────

async def morning_reminder():
    for group in get_all_groups():
        gtype = group["group_type"] or "relaxed"
        if gtype == "tadabbur":
            continue
        chat_id = group["chat_id"]
        group_tasks = get_group_tasks(group)
        glang = get_group_lang(group)
        try:
            missing = get_missing_students(group["id"], group_tasks)
            if not missing:
                continue
            missing_names = [s["name"] for s, _ in missing]
            msg = await ai.group_motivation(missing_names, group["title"] or chat_id, glang)
            if msg:
                await send_message(chat_id, "☀️ " + msg)
            await asyncio.sleep(1)
        except Exception as e:
            log.error("morning_reminder error in %s: %s", chat_id, e)


# ── Личные напоминания (18:00) ─────────────────────────────────────────────────

async def personal_reminders():
    for group in get_all_groups():
        gtype = group["group_type"] or "relaxed"
        if gtype == "tadabbur":
            continue
        group_tasks = get_group_tasks(group)
        glang = get_group_lang(group)
        chat_id = group["chat_id"]
        try:
            for s in get_students(group["id"]):
                if not s["phone"]:
                    continue
                rep = get_today_report(s["id"])
                if rep and all(rep[k] for k in group_tasks):
                    continue
                missed = [k for k in group_tasks if not rep or not rep[k]]
                days = get_consecutive_skips(s["id"])
                msg = await ai.reminder(s["name"], missed, days, glang)
                if msg:
                    await send_message(chat_id, msg)
                await asyncio.sleep(0.8)
        except Exception as e:
            log.error("personal_reminders error in %s: %s", chat_id, e)


# ── Вечерний отчёт (20:00) ────────────────────────────────────────────────────

async def evening_report():
    today = get_date()
    for group in get_all_groups():
        gtype = group["group_type"] or "relaxed"
        chat_id = group["chat_id"]
        group_tasks = get_group_tasks(group)
        glang = get_group_lang(group)
        try:
            report_text = format_daily_report(group["id"], group["title"] or chat_id, group_tasks, today)
            await send_message(chat_id, report_text)

            if gtype == "pro" and group["summary_chat_id"]:
                await send_message(
                    group["summary_chat_id"],
                    "📋 Сводка из про-группы " + (group["title"] or chat_id) + ":\n\n" + report_text
                )

            students = get_students(group["id"])
            full_done = [
                s for s in students
                if (rep := get_today_report(s["id"])) and all(rep[k] for k in group_tasks)
            ]
            if full_done:
                names = [s["name"] for s in full_done]
                praise = await ai.group_praise(names, glang)
                if praise:
                    await send_message(chat_id, "🌟 " + praise)
            await asyncio.sleep(1)
        except Exception as e:
            log.error("evening_report error in %s: %s", chat_id, e)


# ── Предупреждение о пропусках (20:30) ───────────────────────────────────────

async def skip_warnings():
    for group in get_all_groups():
        gtype = group["group_type"] or "relaxed"
        if gtype == "tadabbur":
            continue
        limit = 10 if gtype == "pro" else 20
        warn_threshold = limit // 2
        glang = get_group_lang(group)
        chat_id = group["chat_id"]
        try:
            for s in get_students(group["id"]):
                if not s["phone"]:
                    continue
                skips = get_consecutive_skips(s["id"])
                if skips >= warn_threshold:
                    warn = await ai.warning_skips(s["name"], skips, glang)
                    if warn:
                        await send_message(chat_id, "⚠️ " + warn)
                    await asyncio.sleep(0.8)
        except Exception as e:
            log.error("skip_warnings error in %s: %s", chat_id, e)


# ── Проверка переводов (21:00) ─────────────────────────────────────────────────

async def transfer_check():
    try:
        await run_transfer_checks()
    except Exception as e:
        log.error("transfer_check error: %s", e)


# ── Еженедельный отчёт (воскресенье 19:00) ────────────────────────────────────

async def weekly_report():
    for group in get_all_groups():
        chat_id = group["chat_id"]
        group_tasks = get_group_tasks(group)
        glang = get_group_lang(group)
        try:
            report = format_period_report(group["id"], group["title"] or chat_id, group_tasks, 7)
            await send_message(chat_id, report)

            winner = get_period_winner(group["id"], 7)
            if winner and winner["points"] > 0:
                praise = await ai.winner_praise(winner["name"], "неделю", winner["points"], glang)
                if praise:
                    await send_message(chat_id, praise)
            await asyncio.sleep(1)
        except Exception as e:
            log.error("weekly_report error in %s: %s", chat_id, e)


# ── Ежемесячный отчёт (1-е число 19:00) ──────────────────────────────────────

async def monthly_report():
    for group in get_all_groups():
        chat_id = group["chat_id"]
        group_tasks = get_group_tasks(group)
        glang = get_group_lang(group)
        try:
            report = format_period_report(group["id"], group["title"] or chat_id, group_tasks, 30)
            await send_message(chat_id, report)

            winner = get_period_winner(group["id"], 30)
            if winner and winner["points"] > 0:
                praise = await ai.winner_praise(winner["name"], "месяц", winner["points"], glang)
                if praise:
                    await send_message(chat_id, praise)
            await asyncio.sleep(1)
        except Exception as e:
            log.error("monthly_report error in %s: %s", chat_id, e)

    # Устазу — общая сводка по всем группам
    try:
        if ADMIN_PHONES:
            lines = ["📊 Итог месяца — все группы:"]
            for g in get_all_groups():
                cnt = len(get_students(g["id"]))
                lines.append("• " + (g["title"] or g["chat_id"]) + ": " + str(cnt) + " студентов")
            lines.append("\nАль-хамду лиллях! 🤲")
            for admin_id in ADMIN_PHONES:
                await send_message(admin_id, "\n".join(lines))
    except Exception as e:
        log.error("monthly_report admin summary error: %s", e)


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
                await maybe_run("morning_reminder", morning_reminder)
            elif h == 18 and m == 0:
                await maybe_run("personal_reminders", personal_reminders)
            elif h == 20 and m == 0:
                await maybe_run("evening_report", evening_report)
            elif h == 20 and m == 30:
                await maybe_run("skip_warnings", skip_warnings)
            elif h == 21 and m == 0:
                await maybe_run("transfer_check", transfer_check)
            elif wd == 6 and h == 19 and m == 0:
                await maybe_run("weekly_report", weekly_report)
            elif d == 1 and h == 19 and m == 0:
                await maybe_run("monthly_report", monthly_report)

            await asyncio.sleep(30)

        except Exception as e:
            log.error("Scheduler loop error: %s", e)
            await asyncio.sleep(60)
