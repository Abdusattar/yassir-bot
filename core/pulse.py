"""«Дыхание Яссира» (07.09.2026) — ритм проекта для главного экрана YassirApp.

Считает по ЧАСАМ и ДНЯМ, сколько джамаат сделал: задания студентов
(score_events, category='task') плюс разборы устазов (voice_submissions.
reviewed_at). Это одно и то же дыхание, поэтому разборы идут в общий счёт, а
не отдельным графиком — решение пользователя 07.09.2026.

Аудио-сдачу отдельной строкой НЕ считаем: голосовое в группе тут же
превращается в задание (m/r/t), и если считать оба — одно действие человека
даст два удара.

Обе базы вместе. Мужской и женский боты живут в двух процессах со своими
БД (см. память «Два бота»), но джамаат один: цифры показываем общие, иначе
студент видит четверых вместо ста тридцати. Парная база открывается ТОЛЬКО
на чтение (mode=ro) — чужой процесс пишет в неё сам, и мешать ему нечем.

Время: score_events.created_at хранится в UTC, а date — бишкекская дата
(известная ловушка проекта, см. память project_score_events_timezone_gotcha),
поэтому час сдвигаем на +6. voice_submissions.sent_at/reviewed_at пишутся
через get_now() — они уже локальные, сдвигать нечего.
"""
import logging
import os
import sqlite3
import time

from config import DB, PROFILE
from core.db import db, get_date, get_now

log = logging.getLogger(__name__)

TZ_SHIFT = 6                 # Asia/Bishkek относительно UTC
DAYS_WINDOW = 8              # 7 полных дней назад + сегодня
CACHE_SECONDS = 60           # пульс — не биржевая котировка
TASKS = ("m", "r", "t")      # три ежедневных; остальные (j/n/h) идут в "other"

_cache = {"at": 0.0, "data": None}


def _pair_path():
    """Путь к базе второго бота рядом со своей. None — если её нет (локальная
    разработка, тесты): тогда пульс считается по одной базе и всё работает."""
    other = "female" if PROFILE == "male" else "male"
    path = os.path.join(os.path.dirname(os.path.abspath(DB)), "quran_%s.db" % other)
    return path if os.path.exists(path) else None


def _rows(conn, sql, params=()):
    try:
        return conn.execute(sql, params).fetchall()
    except sqlite3.Error as e:
        log.warning("pulse: запрос не удался (%s)", e)
        return []


def _collect(conn, acc, since):
    """Дописывает в acc данные одной базы. acc — словарь date -> ряды по часам."""
    def day(d):
        return acc.setdefault(d, {
            "total": [0] * 24, "m": [0] * 24, "r": [0] * 24, "t": [0] * 24,
            "other": [0] * 24, "review": [0] * 24, "people": 0,
        })

    for d, sub, h, n in _rows(conn,
            "SELECT date, subcategory,"
            "       ((CAST(strftime('%H', created_at) AS INT) + ?) % 24) h, COUNT(*)"
            " FROM score_events"
            " WHERE category='task' AND date >= ?"
            " GROUP BY date, subcategory, h", (TZ_SHIFT, since)):
        row = day(d)
        row[sub if sub in TASKS else "other"][int(h)] += n
        row["total"][int(h)] += n

    for d, h, n in _rows(conn,
            "SELECT date, CAST(substr(reviewed_at, 12, 2) AS INT) h, COUNT(*)"
            " FROM voice_submissions"
            " WHERE reviewed_at IS NOT NULL AND date >= ?"
            " GROUP BY date, h", (since,)):
        if h is None:
            continue
        row = day(d)
        row["review"][int(h) % 24] += n
        row["total"][int(h) % 24] += n

    for d, n in _rows(conn,
            "SELECT date, COUNT(DISTINCT student_id) FROM score_events"
            " WHERE category='task' AND date >= ? GROUP BY date", (since,)):
        day(d)["people"] += n


def _active_students(conn):
    rows = _rows(conn,
        "SELECT COUNT(DISTINCT ug.user_id) FROM user_groups ug"
        " JOIN groups g ON g.id = ug.group_id"
        " WHERE ug.role='student' AND ug.active=1 AND g.active=1"
        "   AND g.group_type != 'tadabbur'")
    return rows[0][0] if rows else 0


def _last_action(conn):
    """Локальное время последнего действия джамаата, ISO-строкой или None.

    Обе выборки приводим к ОДНОМУ виду "ГГГГ-ММ-ДД ЧЧ:ММ:СС", потому что
    сравниваем строками. score_events.created_at это UTC (см. память про
    часовой пояс), его сдвигаем; voice_submissions.reviewed_at уже локальное,
    но записано через isoformat() - с "T" и смещением "+06:00" на конце.
    Без выравнивания "2026-09-07 21:55:33" оказывалось МЕНЬШЕ, чем
    "2026-09-07T20:18:38+06:00" (пробел меньше буквы "T"), и экран писал
    "тихо, последнее действие 50 минут назад" в тот момент, когда джамаат
    сдавал (живой баг 07.09.2026)."""
    best = None
    for sql in (
        "SELECT MAX(datetime(created_at, '+%d hours')) FROM score_events"
        " WHERE category='task' AND date >= date('now', '-2 day')" % TZ_SHIFT,
        "SELECT MAX(substr(replace(reviewed_at, 'T', ' '), 1, 19))"
        " FROM voice_submissions"
        " WHERE reviewed_at IS NOT NULL AND date >= date('now', '-2 day')",
    ):
        rows = _rows(conn, sql)
        val = rows[0][0] if rows else None
        if val and (best is None or val > best):
            best = val
    return best


def _quiet_minutes(stamps):
    """Сколько минут прошло с последнего действия. None — если непонятно."""
    latest = max([s for s in stamps if s], default=None)
    if not latest:
        return None
    try:
        from datetime import datetime
        txt = latest.replace("T", " ")[:19]
        then = datetime.fromisoformat(txt)
        now = get_now().replace(tzinfo=None)
        return max(0, int((now - then).total_seconds() // 60))
    except (ValueError, TypeError):
        return None


def _compute():
    from datetime import timedelta
    acc, stamps, people_total = {}, [], 0
    since = (get_now().date() - timedelta(days=DAYS_WINDOW - 1)).isoformat()

    with db() as c:
        _collect(c, acc, since)
        stamps.append(_last_action(c))
        people_total += _active_students(c)

    pair = _pair_path()
    if pair:
        conn = None
        try:
            conn = sqlite3.connect("file:%s?mode=ro" % pair.replace("?", "%3f"), uri=True)
            _collect(conn, acc, since)
            stamps.append(_last_action(conn))
            people_total += _active_students(conn)
        except sqlite3.Error as e:
            # Второй бот мог быть остановлен, база — заблокирована или в
            # миграции. Это не повод ронять главный экран: покажем свою
            # половину джамаата.
            log.warning("pulse: парная база недоступна (%s)", e)
        finally:
            if conn is not None:
                conn.close()

    today = get_date()
    days = []
    for d in sorted(acc)[-DAYS_WINDOW:]:
        row = acc[d]
        days.append({
            "date": d,
            "total": row["total"],
            "people": row["people"],
        })
    if not days or days[-1]["date"] != today:
        days.append({"date": today, "total": [0] * 24, "people": 0})

    # Профиль часа — чем именно занят джамаат в этот час суток. Берём неделю
    # целиком, а не вчера: один день слишком дёрганый, чтобы по нему выбирать,
    # какого цвета будет следующая вспышка.
    profile = {k: [0] * 24 for k in ("m", "r", "t", "other", "review")}
    for d, row in acc.items():
        if d == today:
            continue
        for k in profile:
            for h in range(24):
                profile[k][h] += row[k][h]

    cur = acc.get(today, {})
    best = max(days[:-1], key=lambda r: sum(r["total"]), default=None)

    return {
        "days": days,
        "today": {
            "m": sum(cur.get("m", [])), "r": sum(cur.get("r", [])),
            "t": sum(cur.get("t", [])), "other": sum(cur.get("other", [])),
            "review": sum(cur.get("review", [])),
            "people": cur.get("people", 0),
            "hourly": cur.get("total", [0] * 24),
        },
        "profile": profile,
        "best": {"date": best["date"], "total": sum(best["total"])} if best else None,
        "people_total": people_total,
        "quiet_min": _quiet_minutes(stamps),
        "hour": int(get_now().strftime("%H")),
    }


def get_pulse():
    """Кэш на минуту: главный экран открывают часто, а агрегаты за неделю по
    двум базам считать на каждое открытие незачем."""
    now = time.time()
    if _cache["data"] is not None and now - _cache["at"] < CACHE_SECONDS:
        return _cache["data"]
    data = _compute()
    _cache["at"] = now
    _cache["data"] = data
    return data
