import asyncio
import logging
from datetime import datetime, timedelta

import pytz

from config import TZ, SUPER_ADMIN_IDS, CURRICULUM_REVIEWER_ID
from core.db import (
    get_all_groups, get_group_tasks, get_group_lang,
    get_students, get_today_report, get_consecutive_skips, get_skip_count_month,
    format_daily_report, format_period_report, get_period_winner,
    get_missing_students, get_date, get_tadabbur_group, get_students_not_in_tadabbur,
    get_setting, set_setting, add_student, get_streak_days, add_bonus, db,
    get_days_since_last_report, get_daily_task_counts, get_voice_review_stats,
    get_group_admins, get_dm_ok, get_learning_group,
    get_next_part_for_review, count_pending_curriculum_review, set_curriculum_review_message,
    get_next_part_to_publish, mark_curriculum_published
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
    date_str = datetime.strptime(yesterday, "%Y-%m-%d").strftime("%d.%m.%Y")

    if random.random() < 0.5:
        intro_hadith, intro_ayah = sampler.sample_hadith(), None
    else:
        intro_hadith, intro_ayah = None, sampler.sample_ayah()
    intro = await ai.morning_report_intro(hadith=intro_hadith, ayah=intro_ayah)

    groups_info = []
    zero_titles = []
    partial_titles = []
    uzr_names = []

    for group in get_all_groups():
        gtype = group["group_type"] or "relaxed"
        if gtype == "tadabbur":
            continue
        try:
            group_tasks = get_group_tasks(group)
            glang = get_group_lang(group)
            title = group["title"] or str(group["chat_id"])

            counts = get_daily_task_counts(group["id"], group_tasks, yesterday)
            total_tasks = len(group_tasks)
            submitted = [c for c in counts if c["done"] > 0]
            uzr_names.extend(c["name"] + " (" + title + ")" for c in counts if c["excused"])

            full = [c for c in submitted if c["done"] == total_tasks]

            if not submitted:
                if any(not c["excused"] for c in counts):
                    zero_titles.append(title)
            elif not full:
                partial_titles.append(title)
            else:
                full_lines = [
                    c["name"] + " — 🌟" + str(get_streak_days(c["id"], yesterday))
                    for c in full
                ]
                groups_info.append({
                    "title": title,
                    "full_lines": full_lines,
                    "full_count": len(full),
                })

            # Личная насыха несдавшим вчера — один текст на всех
            missing = get_missing_students(group["id"], group_tasks, date=yesterday)
            phones = [s["phone"] for s, _ in missing if s["phone"]]
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

    groups_info.sort(key=lambda g: -g["full_count"])

    lines = []
    if intro:
        lines.append("📖 " + intro)
        lines.append("")
    lines.append("🎉 Сдали ВСЕ задания за " + date_str)
    lines.append("(🌟 — дней подряд без пропуска)")
    for g in groups_info:
        lines.append("")
        lines.append(g["title"])
        lines.extend(g["full_lines"])
    if partial_titles:
        lines.append("")
        lines.append("Группы, где сдали частично: " + ", ".join(partial_titles))
    if zero_titles:
        lines.append("")
        lines.append("Не сдавали вчера ничего: " + ", ".join(zero_titles))
    if uzr_names:
        lines.append("")
        lines.append("⛔ Узр: " + ", ".join(uzr_names))

    await send_message(tadabbur["chat_id"], "\n".join(lines))


# ── Проверка голосовых сдач устазами (12:00, группа «Масштабирование») ───────

# chat_id обновлён 04.07.2026 — группа была апгрейднута до супергруппы,
# старый -5283697370 больше не годится для getChatAdministrators/exportChatInviteLink.
_SCALING_CHAT_ID = "-1004387097146"
_SCALING_INVITE_LINK = "https://t.me/+8IxbNN6MtjY3NDRi"
_VOICE_REVIEW_CHAT_ID = _SCALING_CHAT_ID


def _format_sent_time(sent_at):
    if not sent_at:
        return "?"
    try:
        return datetime.fromisoformat(sent_at).strftime("%H:%M")
    except ValueError:
        return "?"


async def voice_review_report():
    # Смотрим позавчера, отчёт шлём в 07:00 — гарантирует минимум 24 часа
    # на проверку любой сдаче независимо от времени отправки.
    target_date = (datetime.now(pytz.timezone(TZ)) - timedelta(days=2)).date().isoformat()
    date_str = datetime.strptime(target_date, "%Y-%m-%d").strftime("%d.%m.%Y")

    full_titles = []
    partial = []

    for group in get_all_groups():
        gtype = group["group_type"] or "relaxed"
        if gtype == "tadabbur":
            continue
        try:
            title = group["title"] or str(group["chat_id"])
            total, reviewed, unreviewed = get_voice_review_stats(group["id"], target_date)
            if total == 0:
                continue
            if reviewed == total:
                full_titles.append(title + " (" + str(reviewed) + "/" + str(total) + ")")
            else:
                unreviewed_labels = [name + " (" + _format_sent_time(sent_at) + ")" for name, sent_at in unreviewed]
                partial.append((title, reviewed, total, unreviewed_labels))
        except Exception as e:
            log.error("voice_review_report error in %s: %s", group["chat_id"], e)

    if not full_titles and not partial:
        return

    lines = ["🎙 Проверка голосовых за " + date_str]
    if full_titles:
        lines.append("")
        lines.append("✅ Проверено полностью:")
        lines.extend("— " + t for t in full_titles)
    for title, reviewed, total, names in partial:
        lines.append("")
        lines.append(title + " — проверено " + str(reviewed) + "/" + str(total))
        lines.append("Не проверено: " + ", ".join(names))

    await send_message(_VOICE_REVIEW_CHAT_ID, "\n".join(lines))


# ── Операционный отчёт за неделю (пн 07:00, подстраховка вт 07:00, «Масштабирование») ──
# Урок считается проведённым, если хотя бы 1 студент группы отметился «у»/«u»
# (core/handlers.py, category='attendance') за прошедшую неделю (пн-вс).
# Флаг в bot_settings не даёт задвоить отправку во вторник, если пн уже отработал.
# Метрики недели к неделе — считаем ту же статистику за позапрошлую неделю для сравнения.

_WORST_REVIEW_COUNT = 3  # сколько групп с самым низким % проверки показывать (реальные цифры, без порога)


def _metric_tracked_since(table, category=None):
    """Самая ранняя дата записи по метрике — чтобы не сравнивать с неделей,
    когда трекинга этой метрики ещё не существовало (даёт ложный «провал/рост»)."""
    with db() as c:
        if category:
            row = c.execute(
                "SELECT MIN(date) as d FROM " + table + " WHERE category=?", (category,)
            ).fetchone()
        else:
            row = c.execute("SELECT MIN(date) as d FROM " + table).fetchone()
    return row["d"]


def _week_ops_stats(start, end):
    lesson_groups, not_held = 0, []
    task_count = 0
    voice_total, voice_reviewed = 0, 0
    voice_by_group = []
    group_tasks = {}
    for group in get_all_groups():
        if (group["group_type"] or "relaxed") == "tadabbur":
            continue
        title = group["title"] or str(group["chat_id"])
        with db() as c:
            attended = c.execute(
                "SELECT 1 FROM score_events"
                " WHERE group_id=? AND category='attendance' AND date>=? AND date<=?",
                (group["id"], start, end)
            ).fetchone()
            task_n = c.execute(
                "SELECT COUNT(*) as n FROM score_events"
                " WHERE group_id=? AND category='task' AND date>=? AND date<=?",
                (group["id"], start, end)
            ).fetchone()["n"]
            voice_rows = c.execute(
                "SELECT reviewed_at FROM voice_submissions"
                " WHERE group_id=? AND date>=? AND date<=?",
                (group["id"], start, end)
            ).fetchall()
        if attended:
            lesson_groups += 1
        else:
            not_held.append(title)
        task_count += task_n
        group_tasks[group["id"]] = (title, task_n)
        v_total = len(voice_rows)
        v_reviewed = sum(1 for r in voice_rows if r["reviewed_at"])
        voice_total += v_total
        voice_reviewed += v_reviewed
        if v_total > 0:
            voice_by_group.append((title, round(100 * v_reviewed / v_total)))
    voice_by_group.sort(key=lambda x: x[1])
    return {
        "lesson_groups": lesson_groups,
        "total_groups": lesson_groups + len(not_held),
        "not_held": not_held,
        "task_count": task_count,
        "group_tasks": group_tasks,
        "voice_pct": round(100 * voice_reviewed / voice_total) if voice_total else None,
        "worst_review": voice_by_group[:_WORST_REVIEW_COUNT],
    }


def _group_task_diff_lines(cur_group_tasks, prev_group_tasks):
    """Список «Группа: N (стрелка)» по всем группам, отсортированный по названию."""
    lines = []
    for gid, (title, n) in sorted(cur_group_tasks.items(), key=lambda kv: kv[1][0]):
        prev_n = prev_group_tasks.get(gid, (title, 0))[1]
        diff = n - prev_n
        line = "— " + title + ": " + str(n)
        if diff != 0:
            line += " (" + _arrow(diff) + ")"
        lines.append(line)
    return lines


def _top_students_by_points(start, end, limit=10):
    """Топ студентов по сумме баллов (задания+бонусы+посещаемость) за период,
    без участия только в Тадаббуре и без устаза (его личная просьба, как в
    _full_week_students/_streak_leaders)."""
    my_id = SUPER_ADMIN_IDS[0] if SUPER_ADMIN_IDS else None
    with db() as c:
        rows = c.execute("""
            SELECT u.name, u.phone, SUM(e.points) as total_points
            FROM score_events e
            JOIN users u ON u.id = e.student_id
            JOIN groups g ON g.id = e.group_id
            WHERE e.date >= ? AND e.date <= ?
              AND (g.group_type IS NULL OR g.group_type != 'tadabbur')
            GROUP BY e.student_id
            HAVING total_points > 0
            ORDER BY total_points DESC
            LIMIT ?
        """, (start, end, limit + 5)).fetchall()
    result = []
    for r in rows:
        if my_id and r["phone"] == my_id:
            continue
        group = get_learning_group(r["phone"])
        group_title = group["title"] if group else "Тадаббур"
        result.append((r["name"], r["total_points"], group_title))
        if len(result) >= limit:
            break
    return result


def _day_word(n):
    return "день" if n == 1 else ("дня" if 2 <= n <= 4 else "дней")


def _arrow(diff, suffix=""):
    if diff > 0:
        return "↑" + str(diff) + suffix
    if diff < 0:
        return "↓" + str(abs(diff)) + suffix
    return "→0" + suffix


async def weekly_ops_report():
    now = _now()
    week_monday = (now - timedelta(days=now.weekday())).date()
    last_monday = week_monday - timedelta(days=7)
    last_sunday = week_monday - timedelta(days=1)
    prev_monday = last_monday - timedelta(days=7)
    prev_sunday = last_monday - timedelta(days=1)
    week_key = last_monday.isoformat()

    if get_setting("ops_report_week") == week_key:
        return

    try:
        cur = _week_ops_stats(str(last_monday), str(last_sunday))
        prev = _week_ops_stats(str(prev_monday), str(prev_sunday))

        # Сравнение с прошлой неделей показываем только если трекинг метрики
        # существовал всю ту неделю целиком — иначе «просело/выросло» будет
        # артефактом недавно появившейся фичи, а не реальной динамикой.
        prev_start = str(prev_monday)
        lesson_since = _metric_tracked_since("score_events", "attendance")
        task_since = _metric_tracked_since("score_events", "task")
        voice_since = _metric_tracked_since("voice_submissions")
        lesson_prev_covered = lesson_since is not None and lesson_since <= prev_start
        task_prev_covered = task_since is not None and task_since <= prev_start
        voice_prev_covered = voice_since is not None and voice_since <= prev_start

        if cur["total_groups"] > 0:
            lesson_diff = cur["lesson_groups"] - prev["lesson_groups"] if lesson_prev_covered else None
            task_diff_pct = (
                round(100 * (cur["task_count"] - prev["task_count"]) / prev["task_count"])
                if task_prev_covered and prev["task_count"] > 0 else None
            )
            voice_diff_pct = (
                cur["voice_pct"] - prev["voice_pct"]
                if voice_prev_covered and cur["voice_pct"] is not None and prev["voice_pct"] is not None else None
            )

            date_range = last_monday.strftime("%d.%m") + "–" + last_sunday.strftime("%d.%m.%Y")
            lines = ["📊 Итоги недели — " + date_range, ""]

            lesson_line = "🕌 Уроки: " + str(cur["lesson_groups"]) + "/" + str(cur["total_groups"]) + " групп провели урок"
            if lesson_diff is not None and lesson_diff != 0:
                lesson_line += " (" + _arrow(lesson_diff) + " к прошлой неделе)"
            lines.append(lesson_line)
            if cur["not_held"]:
                lines.append("⛔ Не провели урок: " + ", ".join(cur["not_held"]))

            lines.append("")
            task_line = "📝 Сдачи заданий: " + str(cur["task_count"]) + " сдано"
            if task_diff_pct is not None:
                task_line += " (" + _arrow(task_diff_pct, "%") + " к прошлой неделе)"
            lines.append(task_line)
            if task_prev_covered:
                lines.append("")
                lines.append("📈 По группам (неделя к неделе):")
                lines.extend(_group_task_diff_lines(cur["group_tasks"], prev["group_tasks"]))

            lines.append("")
            if cur["voice_pct"] is not None:
                voice_line = "🎙 Проверка таджвида: " + str(cur["voice_pct"]) + "% голосовых проверено"
                if voice_diff_pct is not None:
                    voice_line += " (" + _arrow(voice_diff_pct, " п.п.") + " к прошлой неделе)"
                lines.append(voice_line)
            if cur["worst_review"]:
                worst_str = ", ".join(t + " — " + str(p) + "%" for t, p in cur["worst_review"])
                lines.append("Меньше всего проверено: " + worst_str)

            good, bad = [], []
            if lesson_diff is not None and lesson_diff > 0:
                good.append("больше групп провели урок")
            elif lesson_diff is not None and lesson_diff < 0:
                bad.append("меньше групп провели урок")
            if task_diff_pct is not None and task_diff_pct > 0:
                good.append("выросли сдачи заданий")
            elif task_diff_pct is not None and task_diff_pct < 0:
                bad.append("просели сдачи заданий")
            if voice_diff_pct is not None and voice_diff_pct > 0:
                good.append("чаще проверяете таджвид")
            elif voice_diff_pct is not None and voice_diff_pct < 0:
                bad.append("просела проверка таджвида")

            lines.append("")
            if good and bad:
                lines.append("📌 Вывод: " + ", ".join(good) + " — но " + ", ".join(bad))
            elif bad:
                lines.append("📌 Вывод: " + ", ".join(bad) + " — обратите внимание")
            elif good:
                lines.append("📌 Вывод: " + ", ".join(good) + " — держите темп")
            else:
                lines.append("📌 Вывод: без изменений к прошлой неделе")

            await send_message(_SCALING_CHAT_ID, "\n".join(lines))
    except Exception as e:
        log.error("weekly_ops_report error: %s", e)

    set_setting("ops_report_week", week_key)


# ── Операционный отчёт за месяц (1-е число) — календарный месяц к предыдущему ──

async def monthly_ops_report():
    now = _now()
    first_this_month = now.date().replace(day=1)
    last_prev_month = first_this_month - timedelta(days=1)
    first_prev_month = last_prev_month.replace(day=1)
    last_prev2_month = first_prev_month - timedelta(days=1)
    first_prev2_month = last_prev2_month.replace(day=1)
    month_key = first_prev_month.isoformat()

    if get_setting("ops_report_month") == month_key:
        return

    try:
        cur = _week_ops_stats(str(first_prev_month), str(last_prev_month))
        prev = _week_ops_stats(str(first_prev2_month), str(last_prev2_month))

        prev_start = str(first_prev2_month)
        lesson_since = _metric_tracked_since("score_events", "attendance")
        task_since = _metric_tracked_since("score_events", "task")
        voice_since = _metric_tracked_since("voice_submissions")
        lesson_prev_covered = lesson_since is not None and lesson_since <= prev_start
        task_prev_covered = task_since is not None and task_since <= prev_start
        voice_prev_covered = voice_since is not None and voice_since <= prev_start

        if cur["total_groups"] > 0:
            lesson_diff = cur["lesson_groups"] - prev["lesson_groups"] if lesson_prev_covered else None
            task_diff_pct = (
                round(100 * (cur["task_count"] - prev["task_count"]) / prev["task_count"])
                if task_prev_covered and prev["task_count"] > 0 else None
            )
            voice_diff_pct = (
                cur["voice_pct"] - prev["voice_pct"]
                if voice_prev_covered and cur["voice_pct"] is not None and prev["voice_pct"] is not None else None
            )

            month_label = first_prev_month.strftime("%m.%Y")
            lines = ["📊 Итоги месяца — " + month_label, ""]

            lesson_line = "🕌 Уроки: " + str(cur["lesson_groups"]) + "/" + str(cur["total_groups"]) + " групп провели урок"
            if lesson_diff is not None and lesson_diff != 0:
                lesson_line += " (" + _arrow(lesson_diff) + " к прошлому месяцу)"
            lines.append(lesson_line)
            if cur["not_held"]:
                lines.append("⛔ Не провели урок ни разу: " + ", ".join(cur["not_held"]))

            lines.append("")
            task_line = "📝 Сдачи заданий: " + str(cur["task_count"]) + " сдано"
            if task_diff_pct is not None:
                task_line += " (" + _arrow(task_diff_pct, "%") + " к прошлому месяцу)"
            lines.append(task_line)
            if task_prev_covered:
                lines.append("")
                lines.append("📈 По группам (месяц к месяцу):")
                lines.extend(_group_task_diff_lines(cur["group_tasks"], prev["group_tasks"]))

            lines.append("")
            if cur["voice_pct"] is not None:
                voice_line = "🎙 Проверка таджвида: " + str(cur["voice_pct"]) + "% голосовых проверено"
                if voice_diff_pct is not None:
                    voice_line += " (" + _arrow(voice_diff_pct, " п.п.") + " к прошлому месяцу)"
                lines.append(voice_line)
            if cur["worst_review"]:
                worst_str = ", ".join(t + " — " + str(p) + "%" for t, p in cur["worst_review"])
                lines.append("Меньше всего проверено: " + worst_str)

            good, bad = [], []
            if lesson_diff is not None and lesson_diff > 0:
                good.append("больше групп проводят уроки")
            elif lesson_diff is not None and lesson_diff < 0:
                bad.append("меньше групп проводят уроки")
            if task_diff_pct is not None and task_diff_pct > 0:
                good.append("выросли сдачи заданий")
            elif task_diff_pct is not None and task_diff_pct < 0:
                bad.append("просели сдачи заданий")
            if voice_diff_pct is not None and voice_diff_pct > 0:
                good.append("чаще проверяете таджвид")
            elif voice_diff_pct is not None and voice_diff_pct < 0:
                bad.append("просела проверка таджвида")

            lines.append("")
            if good and bad:
                lines.append("📌 Вывод: " + ", ".join(good) + " — но " + ", ".join(bad))
            elif bad:
                lines.append("📌 Вывод: " + ", ".join(bad) + " — обратите внимание")
            elif good:
                lines.append("📌 Вывод: " + ", ".join(good) + " — держите темп")
            else:
                lines.append("📌 Вывод: без изменений к прошлому месяцу")

            await send_message(_SCALING_CHAT_ID, "\n".join(lines))
    except Exception as e:
        log.error("monthly_ops_report error: %s", e)

    set_setting("ops_report_month", month_key)


# ── Сводка за неделю для «Тадаббур» (вт 12:00) — командный итог для студентов ──
# Отдельно от weekly_ops_report (устазам, операционные метрики) — тут только то,
# что имеет смысл для самих студентов: совокупная сдача + примеры для подражания.
# «Примеры недели»/«Держат планку» исключают только SUPER_ADMIN_IDS[0] (устаз
# Абдусаттар лично), а не всех устазов/супер-админов — его личная просьба.
# Закрытие — аят/хадис без AI: берём кешированный перевод, без него — оригинал.

_TADABBUR_STREAK_THRESHOLD = 7
_TADABBUR_MONTHLY_STREAK_THRESHOLD = 21


def _full_period_students(period_start, period_end):
    my_id = SUPER_ADMIN_IDS[0] if SUPER_ADMIN_IDS else None
    days = [(period_start + timedelta(days=i)).isoformat() for i in range((period_end - period_start).days + 1)]
    names = []
    for group in get_all_groups():
        if (group["group_type"] or "relaxed") == "tadabbur":
            continue
        group_tasks = get_group_tasks(group)
        total_tasks = len(group_tasks)
        if total_tasks == 0:
            continue
        with db() as c:
            rows = c.execute(
                "SELECT student_id, date, COUNT(DISTINCT subcategory) as cnt"
                " FROM score_events WHERE group_id=? AND category='task' AND date>=? AND date<=?"
                " GROUP BY student_id, date",
                (group["id"], days[0], days[-1])
            ).fetchall()
        per_student = {}
        for r in rows:
            per_student.setdefault(r["student_id"], {})[r["date"]] = r["cnt"]
        for s in get_students(group["id"]):
            if my_id and s["phone"] == my_id:
                continue
            day_counts = per_student.get(s["id"], {})
            if all(day_counts.get(d, 0) >= total_tasks for d in days):
                names.append((s["name"], group["title"] or str(group["chat_id"])))
    return names


def _streak_leaders(anchor_date, threshold):
    my_id = SUPER_ADMIN_IDS[0] if SUPER_ADMIN_IDS else None
    result = []
    for group in get_all_groups():
        if (group["group_type"] or "relaxed") == "tadabbur":
            continue
        for s in get_students(group["id"]):
            if my_id and s["phone"] == my_id:
                continue
            streak = get_streak_days(s["id"], anchor_date)
            if streak >= threshold:
                result.append((s["name"], streak, group["title"] or str(group["chat_id"])))
    result.sort(key=lambda x: -x[1])
    return result


async def _closing_verse():
    """Предпочитаем кешированный перевод (без AI); если для выбранной цитаты
    перевода ещё нет — переводим один раз через ai._get_*_translation и кешируем,
    дальше эта же цитата уже отдаётся без AI. Раз в неделю, не ежедневная нагрузка."""
    pick_hadith_first = random.random() < 0.5
    order = (sampler.sample_hadith, sampler.sample_ayah) if pick_hadith_first \
        else (sampler.sample_ayah, sampler.sample_hadith)
    for fn in order:
        item = fn()
        if not item:
            continue
        if "sura" in item:
            text = await ai._get_ayah_translation(item, "ru")
            if text:
                return "📖 " + text + " (" + item["ref"] + ")"
        else:
            text = await ai._get_hadith_translation(item, "ru")
            if text:
                return "📖 " + text + " (" + item.get("label", "") + ")"
    return None


async def weekly_tadabbur_summary():
    tadabbur = get_tadabbur_group()
    if not tadabbur:
        return
    now = _now()
    week_monday = (now - timedelta(days=now.weekday())).date()
    last_monday = week_monday - timedelta(days=7)
    last_sunday = week_monday - timedelta(days=1)
    week_key = last_monday.isoformat()

    if get_setting("tadabbur_summary_week") == week_key:
        return

    try:
        task_count = 0
        for group in get_all_groups():
            if (group["group_type"] or "relaxed") == "tadabbur":
                continue
            with db() as c:
                task_n = c.execute(
                    "SELECT COUNT(*) as n FROM score_events"
                    " WHERE group_id=? AND category='task' AND date>=? AND date<=?",
                    (group["id"], str(last_monday), str(last_sunday))
                ).fetchone()["n"]
            task_count += task_n

        if task_count > 0:
            full_week_names = _full_period_students(last_monday, last_sunday)
            streak_leaders = _streak_leaders(str(last_sunday), _TADABBUR_STREAK_THRESHOLD)
            top_students = _top_students_by_points(str(last_monday), str(last_sunday), 10)

            date_range = last_monday.strftime("%d.%m") + "–" + last_sunday.strftime("%d.%m.%Y")
            lines = ["📊 Итоги недели — вся община (" + date_range + ")", ""]
            lines.append("Вместе за неделю сдано " + str(task_count) + " заданий 🤲")

            if full_week_names:
                lines.append("")
                lines.append("🌟 Примеры недели (сдавали всё всю неделю):")
                lines.extend("— " + n + " (" + g + ")" for n, g in full_week_names)

            if streak_leaders:
                lines.append("")
                lines.append("🔥 Держат планку (" + str(_TADABBUR_STREAK_THRESHOLD) + "+ дней подряд):")
                lines.extend("— " + n + " (" + g + ") — " + str(d) + " " + _day_word(d) for n, d, g in streak_leaders)

            if top_students:
                lines.append("")
                lines.append("🏆 Топ-10 недели:")
                lines.extend(
                    str(i + 1) + ". " + n + " (" + g + ") — " + str(p) + " баллов"
                    for i, (n, p, g) in enumerate(top_students)
                )

            verse = await _closing_verse()
            if verse:
                lines.append("")
                lines.append(verse)

            await send_message(tadabbur["chat_id"], "\n".join(lines))
    except Exception as e:
        log.error("weekly_tadabbur_summary error: %s", e)

    set_setting("tadabbur_summary_week", week_key)


# ── Сводка за месяц для «Тадаббур» (1-е число) — подбадривающая, для студентов ─

async def monthly_tadabbur_summary():
    tadabbur = get_tadabbur_group()
    if not tadabbur:
        return
    now = _now()
    first_this_month = now.date().replace(day=1)
    last_prev_month = first_this_month - timedelta(days=1)
    first_prev_month = last_prev_month.replace(day=1)
    month_key = first_prev_month.isoformat()

    if get_setting("tadabbur_summary_month") == month_key:
        return

    try:
        task_count = 0
        for group in get_all_groups():
            if (group["group_type"] or "relaxed") == "tadabbur":
                continue
            with db() as c:
                task_n = c.execute(
                    "SELECT COUNT(*) as n FROM score_events"
                    " WHERE group_id=? AND category='task' AND date>=? AND date<=?",
                    (group["id"], str(first_prev_month), str(last_prev_month))
                ).fetchone()["n"]
            task_count += task_n

        if task_count > 0:
            full_month_names = _full_period_students(first_prev_month, last_prev_month)
            streak_leaders = _streak_leaders(str(last_prev_month), _TADABBUR_MONTHLY_STREAK_THRESHOLD)
            top_students = _top_students_by_points(str(first_prev_month), str(last_prev_month), 10)

            month_label = first_prev_month.strftime("%m.%Y")
            lines = ["📊 Итоги месяца — вся община (" + month_label + ")", ""]
            lines.append("Вместе за месяц сдано " + str(task_count) + " заданий 🤲")

            if full_month_names:
                lines.append("")
                lines.append("🌟 Примеры месяца (сдавали всё каждый день весь месяц):")
                lines.extend("— " + n + " (" + g + ")" for n, g in full_month_names)

            if streak_leaders:
                lines.append("")
                lines.append("🔥 Держат планку (" + str(_TADABBUR_MONTHLY_STREAK_THRESHOLD) + "+ дней подряд):")
                lines.extend("— " + n + " (" + g + ") — " + str(d) + " " + _day_word(d) for n, d, g in streak_leaders)

            if top_students:
                lines.append("")
                lines.append("🏆 Топ-10 месяца:")
                lines.extend(
                    str(i + 1) + ". " + n + " (" + g + ") — " + str(p) + " баллов"
                    for i, (n, p, g) in enumerate(top_students)
                )

            verse = await _closing_verse()
            if verse:
                lines.append("")
                lines.append(verse)

            await send_message(tadabbur["chat_id"], "\n".join(lines))
    except Exception as e:
        log.error("monthly_tadabbur_summary error: %s", e)

    set_setting("tadabbur_summary_month", month_key)


# ── Программа обучения: нахв/таджвид по частям, с одобрением устаза ───────────
# Каждая часть готовится заранее (не генерируется на лету), шлётся устазу в
# личку на одобрение (👍 → mark_curriculum_approved, core/handlers.py), и только
# после этого может быть опубликована студентам. См. wiki/curriculum.md.

_SUBJECT_TASK_KEY = {"n": "n", "j": "j"}  # subject == буква задания в groups.tasks
_REVIEW_BUFFER = 3  # держим у устаза на рассмотрении до 3 частей вперёд


async def request_curriculum_review():
    """Держим у устаза буфер из _REVIEW_BUFFER частей на рассмотрении —
    досылаем недостающие, не ждём одобрения каждой по одной."""
    if not CURRICULUM_REVIEWER_ID:
        return
    for subject in _SUBJECT_TASK_KEY:
        try:
            while count_pending_curriculum_review(subject) < _REVIEW_BUFFER:
                part = get_next_part_for_review(subject)
                if not part:
                    break
                label = "Нахв" if subject == "n" else "Таджвид"
                text = (
                    "📘 " + label + " — скоро уйдёт в группы по расписанию\n"
                    + part["chapter"] + " → " + part["topic"]
                    + " (часть " + str(part["part_number"]) + "/" + str(part["part_total"]) + ")\n\n"
                    + part["content"]
                    + "\n\n— если есть ошибка, напиши, поправим до или после публикации"
                )
                resp = await tg_call("sendMessage", {"chat_id": CURRICULUM_REVIEWER_ID, "text": text})
                if resp and resp.get("ok"):
                    msg_id = resp["result"]["message_id"]
                    set_curriculum_review_message(part["id"], CURRICULUM_REVIEWER_ID, msg_id)
                else:
                    break
                # Копия остальным супер-админам — просто для информации,
                # на одобрение влияет только 👍 от CURRICULUM_REVIEWER_ID.
                for admin_id in SUPER_ADMIN_IDS:
                    if admin_id == CURRICULUM_REVIEWER_ID:
                        continue
                    try:
                        await tg_call("sendMessage", {
                            "chat_id": admin_id,
                            "text": "ℹ️ Отправлено устазу на одобрение:\n\n" + text
                        })
                    except Exception as e:
                        log.error("request_curriculum_review copy error for admin=%s: %s", admin_id, e)
                await asyncio.sleep(0.3)
        except Exception as e:
            log.error("request_curriculum_review error for subject=%s: %s", subject, e)


async def publish_curriculum_parts():
    """Публикует следующую часть по очереди в группы с соответствующим заданием.
    Не ждёт одобрения устаза (решение от 08.07.2026) — только видимость заранее
    через request_curriculum_review. Нет части в очереди → безопасный no-op."""
    for subject, task_key in _SUBJECT_TASK_KEY.items():
        try:
            part = get_next_part_to_publish(subject)
            if not part:
                continue
            label = "Нахв" if subject == "n" else "Таджвид"
            text = (
                "📘 " + label + ": " + part["chapter"] + " — " + part["topic"]
                + " (часть " + str(part["part_number"]) + "/" + str(part["part_total"]) + ")\n\n"
                + part["content"]
            )
            for group in get_all_groups():
                gtype = group["group_type"] or "relaxed"
                if gtype == "tadabbur":
                    continue
                if task_key not in get_group_tasks(group):
                    continue
                try:
                    await send_message(group["chat_id"], text)
                    await asyncio.sleep(0.3)
                except Exception as e:
                    log.error("publish_curriculum_parts send error in %s: %s", group["chat_id"], e)
            mark_curriculum_published(part["id"])
        except Exception as e:
            log.error("publish_curriculum_parts error for subject=%s: %s", subject, e)


# ── Приглашение устазов в «Масштабирование» (21:00) ──────────────────────────
# Устаз = user_groups.role='admin' (назначается командой /admin реплаем) —
# это и есть источник, который реально читает is_group_admin().

async def invite_missing_ustaz_to_scaling():
    ustaz_ids = set()
    for group in get_all_groups():
        for phone in get_group_admins(group["id"]):
            if phone and phone not in SUPER_ADMIN_IDS:
                ustaz_ids.add(phone)

    text = (
        "Ассаляму алейкум! 🕌\n"
        "Присоединяйтесь к группе «Масштабирование» — там утренние сводки по группам:\n"
        + _SCALING_INVITE_LINK
    )

    for uid in ustaz_ids:
        try:
            needs_invite = True
            member_resp = await tg_call("getChatMember", {"chat_id": _SCALING_CHAT_ID, "user_id": int(uid)})
            if member_resp and member_resp.get("ok"):
                status = member_resp["result"].get("status")
                if status not in ("left", "kicked"):
                    needs_invite = False
            if needs_invite:
                await send_message(uid, text)
                await asyncio.sleep(0.5)
        except Exception as e:
            log.error("invite_missing_ustaz: error for uid=%s: %s", uid, e)


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
                if not s["phone"]:
                    continue
                missed = get_days_since_last_report(s["id"], group["id"])
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


# ── Напоминание подключить ЛС с ботом (08:00) ────────────────────────────────
# Telegram не даёт боту написать студенту первым, пока тот сам не напишет боту
# хотя бы раз (users.dm_ok). Без этого не работают личные напоминания и
# предупреждения о пропусках. Единственный канал достучаться до таких студентов —
# групповой чат, где бот уже состоит: публикуем ссылку-приглашение только для тех,
# кто ещё не подключился; группа, где все уже подключены, ничего не получает.

async def dm_connect_reminder():
    me = await tg_call("getMe")
    username = (me or {}).get("result", {}).get("username") if me else None
    if not username:
        log.error("dm_connect_reminder: getMe failed, skip")
        return
    link = "https://t.me/" + username + "?start=go"

    for group in get_all_groups():
        if (group["group_type"] or "relaxed") == "tadabbur":
            continue
        chat_id = group["chat_id"]
        try:
            pending = [s["name"] for s in get_students(group["id"]) if s["phone"] and not get_dm_ok(s["id"])]
            if not pending:
                continue
            await send_message(
                chat_id,
                "🔔 " + ", ".join(pending) + " — чтобы бот мог присылать личные "
                "напоминания и предупреждения, перейди по ссылке и нажми Start (один раз):\n" + link
            )
            await asyncio.sleep(1)
        except Exception as e:
            log.error("dm_connect_reminder error in %s: %s", chat_id, e)


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
                    skips = get_skip_count_month(s["id"], group["id"])
                    warn_threshold = 5
                    transfer_limit = 10
                else:
                    skips = get_skip_count_month(s["id"], group["id"])
                    warn_threshold = 15
                    transfer_limit = 20
                if skips >= warn_threshold:
                    warn = await ai.warning_skips(s["name"], skips, transfer_limit, glang, hadith=hadith, ayah=ayah)
                    if warn:
                        await send_message(s["phone"], "⚠️ " + warn)
                    await asyncio.sleep(0.8)
        except Exception as e:
            log.error("skip_warnings error in %s: %s", chat_id, e)


# ── Ежедневная насыха в Тадаббур (09:00) ─────────────────────────────────────

async def tadabbur_nasiha():
    tadabbur = get_tadabbur_group()
    if not tadabbur:
        return
    hadith = sampler.sample_hadith()
    ayah   = sampler.sample_ayah()
    try:
        text = await ai.group_motivation_base(
            "ru", "relaxed", hadith=hadith, ayah=ayah,
            model="google/gemini-2.5-pro", max_tokens=3000
        )
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
                await maybe_run("voice_review_report", voice_review_report)
                if wd in (0, 1):
                    await maybe_run("weekly_ops_report", weekly_ops_report)
                if d in (1, 2):
                    await maybe_run("monthly_ops_report", monthly_ops_report)
                    await maybe_run("monthly_tadabbur_summary", monthly_tadabbur_summary)
            elif h == 9 and m == 0:
                await maybe_run("tadabbur_nasiha", tadabbur_nasiha)
            elif wd == 1 and h == 12 and m == 0:
                await maybe_run("weekly_tadabbur_summary", weekly_tadabbur_summary)
            elif h == 8 and m == 0:
                await maybe_run("dm_connect_reminder", dm_connect_reminder)
                if wd == 3:
                    await maybe_run("publish_curriculum_parts", publish_curriculum_parts)
            elif h == 15 and m == 0:
                await maybe_run("individual_reminders", individual_reminders)
            elif h == 20 and m == 30:
                await maybe_run("skip_warnings", skip_warnings)
            elif h == 21 and m == 0:
                await maybe_run("transfer_check", transfer_check)
                await maybe_run("prep_check", check_prep_students)
                await maybe_run("invite_missing_ustaz_to_scaling", invite_missing_ustaz_to_scaling)
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
