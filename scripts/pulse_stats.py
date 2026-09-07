#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ритм проекта по часам — данные для «дыхания Яссира».

Считает по обеим базам (мужская + женская) за последние N дней:
  - сдачи (voice_submissions) по часам,
  - задания (score_events) по типу и по часам,
  - разборы устаза по часам.

ВАЖНО: score_events.created_at хранится в UTC, а date — бишкекская дата
(известная ловушка проекта). Поэтому час сдвигаем на +6.

Запуск:  python3 pulse_stats.py [дней]   (по умолчанию 7)
"""
import json
import sqlite3
import sys

DBS = {
    "male": "/home/stursunkul/yassir-bot/quran_male.db",
    "female": "/home/stursunkul/yassir-bot/quran_female.db",
}
TZ_SHIFT = 6          # Asia/Bishkek относительно UTC
TASKS = ("m", "r", "t")


def hours_row(cur, sql, params):
    out = [0] * 24
    for h, n in cur.execute(sql, params):
        if h is None:
            continue
        out[int(h) % 24] += n
    return out


def collect(days):
    res = {"days": days, "submissions": {}, "reviews": {}, "tasks": {}}
    for who, path in DBS.items():
        c = sqlite3.connect(path)
        since = "-%d day" % days
        res["submissions"][who] = hours_row(
            c,
            "SELECT CAST(substr(sent_at, 12, 2) AS INT) h, COUNT(*)"
            " FROM voice_submissions WHERE date >= date('now', ?) GROUP BY h",
            (since,))
        res["reviews"][who] = hours_row(
            c,
            "SELECT CAST(substr(reviewed_at, 12, 2) AS INT) h, COUNT(*)"
            " FROM voice_submissions"
            " WHERE reviewed_at IS NOT NULL AND date >= date('now', ?) GROUP BY h",
            (since,))
        res["tasks"][who] = {}
        for task in TASKS:
            res["tasks"][who][task] = hours_row(
                c,
                "SELECT ((CAST(strftime('%H', created_at) AS INT) + ?) % 24) h, COUNT(*)"
                " FROM score_events"
                " WHERE category='task' AND subcategory=? AND date >= date('now', ?)"
                " GROUP BY h",
                (TZ_SHIFT, task, since))
        c.close()
    return res


def merged(res, key, sub=None):
    out = [0] * 24
    for who in DBS:
        row = res[key][who][sub] if sub else res[key][who]
        for i in range(24):
            out[i] += row[i]
    return out




# --- ритм по дням: для листаемой волны в «дыхании» ------------------------
# Экран показывает не только сегодня: волну можно листать назад, поэтому
# нужна матрица «день × час». Считаем то же, что и в общем пульсе:
# задания студентов + разборы устаза (см. by_day ниже).

def by_day(days):
    """[{date, total[24], task_m[24], task_r[24], task_t[24], other[24],
        reviews[24], people}] — по одному элементу на день, старые первыми."""
    acc = {}
    for path in DBS.values():
        c = sqlite3.connect(path)
        c.row_factory = sqlite3.Row
        since = "-%d day" % days
        rows = c.execute(
            "SELECT date d, subcategory sub,"
            "       ((CAST(strftime('%H', created_at) AS INT) + ?) % 24) h,"
            "       COUNT(*) n"
            " FROM score_events"
            " WHERE category='task' AND date >= date('now', ?)"
            " GROUP BY d, sub, h", (TZ_SHIFT, since)).fetchall()
        for r in rows:
            day = acc.setdefault(r["d"], {})
            key = r["sub"] if r["sub"] in TASKS else "other"
            day.setdefault(key, [0] * 24)[r["h"]] += r["n"]
            day.setdefault("total", [0] * 24)[r["h"]] += r["n"]
        for r in c.execute(
                "SELECT date d, CAST(substr(reviewed_at, 12, 2) AS INT) h, COUNT(*) n"
                " FROM voice_submissions"
                " WHERE reviewed_at IS NOT NULL AND date >= date('now', ?)"
                " GROUP BY d, h", (since,)).fetchall():
            if r["h"] is None:
                continue
            day = acc.setdefault(r["d"], {})
            # Разбор устаза — такое же действие джамаата, идёт в общую волну.
            day.setdefault("reviews", [0] * 24)[r["h"] % 24] += r["n"]
            day.setdefault("total", [0] * 24)[r["h"] % 24] += r["n"]
        for r in c.execute(
                "SELECT date d, COUNT(DISTINCT student_id) n FROM score_events"
                " WHERE category='task' AND date >= date('now', ?) GROUP BY d",
                (since,)).fetchall():
            acc.setdefault(r["d"], {})["people"] = \
                acc.setdefault(r["d"], {}).get("people", 0) + r["n"]
        c.close()

    out = []
    for d in sorted(acc):
        row = {"date": d, "people": acc[d].get("people", 0)}
        for k in ("total", "reviews", "other") + TASKS:
            row[k] = acc[d].get(k, [0] * 24)
        out.append(row)
    return out


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    days = int(args[0]) if args else 7
    if "--by-day" in sys.argv:
        print(json.dumps({"days": days, "rows": by_day(days)}, ensure_ascii=False))
    else:
        res = collect(days)
        print(json.dumps({
            "days": days,
            "submissions": merged(res, "submissions"),
            "reviews": merged(res, "reviews"),
            "task_m": merged(res, "tasks", "m"),
            "task_r": merged(res, "tasks", "r"),
            "task_t": merged(res, "tasks", "t"),
        }, ensure_ascii=False))
