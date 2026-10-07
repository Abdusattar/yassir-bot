"""Мини-отчёт по одному дню студента (07.10.2026, решение пользователя).

Зачем. В «Моём месяце» день посветлее значит «сдано не всё», но что именно
не сдано - не видно, и каждый такой случай разбирался руками (Сумая, 2
группа Асмы: «я всё сдаю», а не хватало повторения). Тап по неполному дню
теперь показывает из базы: что сдано и во сколько, чего не хватило, узр,
урок - и короткий след действий в приложении за этот день. Одна и та же
картина у студента и у устаза в «Студентах»: прозрачность снимает спор.

Ничего не считает заново - только читает score_events, voice_submissions,
revision_recordings, дневные слова тренажёра и app_trail. День - учебный
(до трёх ночи, core/db.get_date), время - местное.
"""
from datetime import datetime, timedelta

import pytz

import core.app_trail as app_trail
import core.mufradat as mufradat
from config import TZ
from core.db import (
    db, get_group_by_id, get_group_tasks, student_tasks, hafiz_ids,
    STUDY_DAY_END_HOUR,
)

TASK_RU = {"m": "заучивание", "r": "повторение", "t": "слова",
           "j": "таджвид", "n": "нахв", "h": "хадис"}

# Что из следа стоит показывать человеку: действия, а не навигация по листам.
_TRAIL_RU = {
    "open": "открыл приложение", "rec": "запись", "submit": "отправил сдачу",
    "retake": "пересдача", "rev_open": "открыл запись повторения",
    "rev_broken": "запись повторения прервалась", "rev_submit": "отправил повторение",
    "enter": "вошёл в заучивание", "audio": "слушал запись",
}
_TRAIL_MAX = 14


def _local_hhmm(ts):
    """'2026-10-07 00:31:59' (UTC, score_events) или ISO с зоной (sent_at,
    app_trail) -> 'ЧЧ:ММ' по TZ. Непонятное - пусто."""
    if not ts:
        return ""
    try:
        t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        try:
            t = datetime.strptime(str(ts)[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return ""
    if t.tzinfo is None:
        t = pytz.utc.localize(t)
    return t.astimezone(pytz.timezone(TZ)).strftime("%H:%M")


def study_day_bounds_utc(date_str):
    """Учебный день D - с 03:00 D по 03:00 D+1 местного времени, в UTC ISO."""
    tz = pytz.timezone(TZ)
    start = tz.localize(datetime.strptime(date_str, "%Y-%m-%d") + timedelta(hours=STUDY_DAY_END_HOUR))
    end = start + timedelta(days=1)
    return start.astimezone(pytz.utc).isoformat(), end.astimezone(pytz.utc).isoformat()


def _place(row):
    page, line, stage = row["hifz_page"], row["hifz_line"], row["hifz_stage"]
    if page is None:
        return ""
    if stage == 3:
        return "стр. %s, лист" % page
    if stage == 2:
        return "стр. %s, половина от строки %s" % (page, (line or 0) + 1)
    return "стр. %s, строка %s" % (page, (line or 0) + 1)


_VERDICT_RU = {"accepted": "принято", "retake": "на пересдачу"}


def _words_today(phone, date_str):
    """Сколько слов прошёл в тренажёре в этот день и сколько из них верно
    (разные слова, как и считает зачёт)."""
    import sqlite3
    try:
        with sqlite3.connect(mufradat.HADITHS_DB, timeout=5) as conn:
            mufradat._ensure_daily_answered_schema(conn)
            row = conn.execute(
                "SELECT COUNT(DISTINCT word_id), COUNT(DISTINCT CASE WHEN correct THEN word_id END)"
                " FROM mufradat_daily_answered_words WHERE user_id=? AND date=?",
                (str(phone), date_str)).fetchone()
            return int(row[0] or 0), int(row[1] or 0)
    except Exception:
        return 0, 0


def day_report(student_id, group_id, date_str, phone=None):
    """Словарь для экрана: tasks (по порядку заданий группы), excuse, lesson,
    trail. Нет группы - None."""
    group = get_group_by_id(group_id)
    if not group:
        return None
    keys = student_tasks(student_id, get_group_tasks(group), hafiz_ids(group_id))
    with db() as c:
        events = c.execute(
            "SELECT category, subcategory, points, note, created_at FROM score_events"
            " WHERE student_id=? AND group_id=? AND date=? ORDER BY created_at",
            (student_id, group_id, date_str)).fetchall()
        subs = c.execute(
            "SELECT hifz_page, hifz_line, hifz_stage, verdict, duration, sent_at, review_type"
            " FROM voice_submissions WHERE student_id=? AND group_id=? AND date=?"
            " AND hifz_page IS NOT NULL ORDER BY sent_at",
            (student_id, group_id, date_str)).fetchall()
        revs = c.execute(
            "SELECT duration, sent_at FROM revision_recordings"
            " WHERE student_id=? AND group_id=? AND date=? ORDER BY sent_at",
            (student_id, group_id, date_str)).fetchall()
    done_at = {}
    excuse = None
    lesson = False
    for e in events:
        if e["category"] == "task":
            done_at.setdefault(e["subcategory"], _local_hhmm(e["created_at"]))
        elif e["category"] == "excuse":
            excuse = e["note"] or ""
        elif e["category"] == "attendance" and e["subcategory"] == "online":
            lesson = True

    tasks = []
    for k in keys:
        item = {"key": k, "name": TASK_RU.get(k, k), "done": k in done_at,
                "at": done_at.get(k), "detail": None}
        if k == "m" and subs:
            parts = []
            for s in subs:
                verdict = _VERDICT_RU.get(s["verdict"], "на проверке")
                parts.append("%s · %s" % (_place(s), verdict))
            item["detail"] = "; ".join(parts)
        elif k == "r" and revs:
            item["detail"] = "; ".join(
                "запись %d мин" % max(1, round((r["duration"] or 0) / 60)) for r in revs)
        elif k == "t" and phone and item["done"]:
            n, ok = _words_today(phone, date_str)
            if n:
                item["detail"] = "%d слов, %d верно" % (n, ok)
        tasks.append(item)

    trail = []
    if phone:
        since, until = study_day_bounds_utc(date_str)
        for ev in app_trail.get_trail_between(phone, since, until):
            label = _TRAIL_RU.get(ev["event"])
            if not label:
                continue
            bits = [_local_hhmm(ev["ts"]), label]
            if ev["event"] in ("submit", "retake") and ev.get("page"):
                bits.append(_place({"hifz_page": ev["page"], "hifz_line": ev.get("line"),
                                    "hifz_stage": ev.get("stage")}))
            elif ev["event"] == "open" and ev.get("note"):
                bits.append(str(ev["note"]).split(" · ")[0])
            elif ev["event"] in ("rev_broken", "rec") and ev.get("note"):
                bits.append(str(ev["note"]))
            trail.append(" · ".join(b for b in bits if b))
            if len(trail) >= _TRAIL_MAX:
                break

    return {"date": date_str, "tasks": tasks, "excuse": excuse, "lesson": lesson, "trail": trail}
