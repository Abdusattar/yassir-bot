"""Кто из студентов живёт не по Бишкеку (21.09.2026).

Приложение присылает пояс телефона (users.tz, IANA-имя). Пока он только
копится - учебный день считается по Бишкеку у всех. Этот отчёт отвечает на
вопрос «скольких вообще касается»: у кого пояс другой и на сколько часов.
NULL - приложение не открывали после выкладки, по умолчанию Бишкек.

    python scripts/user_timezones.py --profile male
    python scripts/user_timezones.py --profile female

Только читает. Запускать на сервере из корня репозитория от stursunkul.
"""
import argparse
import os
import pathlib
import sqlite3
from datetime import datetime

import pytz

ROOT = pathlib.Path(__file__).resolve().parent.parent
HOME = "Asia/Bishkek"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--profile", default="male", choices=["male", "female"])
    args = ap.parse_args()
    db_path = os.environ.get("DB_PATH") or str(ROOT / f"quran_{args.profile}.db")

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT u.name, u.tz, COALESCE(g.title, '-') AS grp FROM users u "
        "LEFT JOIN user_groups ug ON ug.user_id = u.id AND ug.active = 1 "
        "LEFT JOIN groups g ON g.id = ug.group_id "
        "WHERE u.active = 1 GROUP BY u.id ORDER BY u.tz, g.title, u.name").fetchall()

    now = datetime.utcnow()
    home = pytz.timezone(HOME).utcoffset(now)
    unknown = [r for r in rows if not r["tz"]]
    same, other = [], []
    for r in rows:
        if not r["tz"]:
            continue
        diff = (pytz.timezone(r["tz"]).utcoffset(now) - home).total_seconds() / 3600
        (same if diff == 0 else other).append((r, diff))

    print(f"база: {db_path}")
    print(f"активных {len(rows)}: пояс как в Бишкеке {len(same)}, другой {len(other)}, "
          f"неизвестен {len(unknown)} (считаются по Бишкеку)")
    for r, diff in sorted(other, key=lambda x: x[1]):
        print(f"  {diff:+5.1f} ч  {r['tz']:<22} {r['name']} ({r['grp']})")


if __name__ == "__main__":
    main()
