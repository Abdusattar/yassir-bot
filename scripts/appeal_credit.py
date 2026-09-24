"""Апелляция: закрыть день студенту, чтобы не рвалась серия (24.09.2026).

Стрик считается по дням, когда есть ВСЕ задания группы (db._full_task_dates).
Если день не закрыт по вине бота (первый случай - Муслим из N-1, 22.09: в
день рубильника бот ответил «зачёт!» на отчёт с таджвидом и повторением,
которые уже принимались только в приложении), недостающие задания
дописываются с нулём баллов: серия восстанавливается, рейтинг не растёт.

    python scripts/appeal_credit.py --profile male --user-id 1 --group N-1 --date 2026-09-22 --why "..."
    python scripts/appeal_credit.py --profile male --user-id 1 --group N-1 --date 2026-09-22 --undo
    python scripts/appeal_credit.py --profile male --user-id 1 --group N-1 --date 2026-09-22   # что есть

Запускать на сервере из корня репозитория от владельца базы (stursunkul).
"""
import argparse
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
NOTE_PREFIX = "апелляция: "


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="male", choices=["male", "female"])
    ap.add_argument("--user-id", type=int, required=True)
    ap.add_argument("--group", required=True, help="название группы, как в базе")
    ap.add_argument("--date", required=True, help="учебный день YYYY-MM-DD")
    ap.add_argument("--why", help="причина - пишется в note; без неё только показать")
    ap.add_argument("--undo", action="store_true")
    a = ap.parse_args()

    os.environ["BOT_PROFILE"] = a.profile
    os.environ.setdefault("DB_PATH", str(ROOT / ("quran_%s.db" % a.profile)))
    sys.path.insert(0, str(ROOT))
    from core.db import db, get_group_tasks, get_streak_days   # noqa: E402

    with db() as c:
        g = c.execute("SELECT * FROM groups WHERE title=?", (a.group,)).fetchone()
        u = c.execute("SELECT id, name FROM users WHERE id=?", (a.user_id,)).fetchone()
    if not g or not u:
        print("нет группы «%s» или пользователя %s" % (a.group, a.user_id))
        return 1
    tasks = get_group_tasks(g)

    with db() as c:
        if a.undo:
            n = c.execute("DELETE FROM score_events WHERE student_id=? AND group_id=? AND date=?"
                          " AND category='task' AND note LIKE ?",
                          (u["id"], g["id"], a.date, NOTE_PREFIX + "%")).rowcount
            print("снято дописанных заданий: %d" % n)
        elif a.why:
            have = {r["subcategory"] for r in c.execute(
                "SELECT subcategory FROM score_events WHERE student_id=? AND group_id=?"
                " AND date=? AND category='task'", (u["id"], g["id"], a.date))}
            missing = [k for k in tasks if k not in have]
            for k in missing:
                c.execute("INSERT OR IGNORE INTO score_events"
                          "(student_id,group_id,date,category,subcategory,points,note)"
                          " VALUES(?,?,?,'task',?,0,?)",
                          (u["id"], g["id"], a.date, k, NOTE_PREFIX + a.why))
            print("дописано с нулём баллов: %s" % (", ".join(missing) or "ничего, день уже полный"))
        rows = c.execute("SELECT subcategory, points, note FROM score_events WHERE student_id=?"
                         " AND group_id=? AND date=? AND category='task'",
                         (u["id"], g["id"], a.date)).fetchall()
    print("%s, «%s», %s:" % (u["name"], g["title"], a.date))
    for r in rows:
        print("  %s  %s балл  %s" % (r["subcategory"], r["points"], r["note"] or ""))
    print("серия сейчас: %d" % get_streak_days(u["id"], g["id"], tasks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
