"""Закрыть письменную сдачу задания в группе с даты (23.09.2026).

Группы «только через YassirApp» пока сдают нахв и хадис письменно
(handlers.APP_ONLY_WRITTEN_KEYS). Когда тренажёр прижился, письменную сдачу
закрываем по группе - первой N-1 по нахву (решение пользователя).

    python scripts/written_off.py --profile male --group N-1 --key n --since 2026-09-24
    python scripts/written_off.py --profile male --group N-1 --key n --undo
    python scripts/written_off.py --profile male               # что закрыто

Запускать на сервере из корня репозитория от владельца базы (stursunkul).
"""
import argparse
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="male", choices=["male", "female"])
    ap.add_argument("--group", help="название группы, как в базе")
    ap.add_argument("--key", choices=["n", "h"])
    ap.add_argument("--since", help="с какой даты (YYYY-MM-DD) письменно не принимать")
    ap.add_argument("--undo", action="store_true")
    a = ap.parse_args()

    os.environ["BOT_PROFILE"] = a.profile
    os.environ.setdefault("DB_PATH", str(ROOT / ("quran_%s.db" % a.profile)))
    sys.path.insert(0, str(ROOT))
    from core.db import db, set_setting, delete_setting   # noqa: E402

    if a.group and a.key:
        with db() as c:
            g = c.execute("SELECT id, title FROM groups WHERE title=?", (a.group,)).fetchone()
        if not g:
            print("нет группы «%s»" % a.group)
            return 1
        key = "written_off:%s:%s" % (g["id"], a.key)
        if a.undo:
            delete_setting(key)
            print("«%s»: письменная сдача %s снова принимается" % (g["title"], a.key))
        elif a.since:
            set_setting(key, a.since)
            print("«%s»: %s письменно не принимается с %s" % (g["title"], a.key, a.since))
    with db() as c:
        rows = c.execute("SELECT s.key, s.value, g.title FROM bot_settings s "
                         "LEFT JOIN groups g ON g.id = CAST(substr(s.key, 13, "
                         "instr(substr(s.key, 13), ':') - 1) AS INTEGER) "
                         "WHERE s.key LIKE 'written_off:%'").fetchall()
    for r in rows:
        print("  %s (%s): с %s" % (r["title"], r["key"], r["value"]))
    if not rows:
        print("  закрытых нет")
    return 0


if __name__ == "__main__":
    sys.exit(main())
