"""С какого дня задание обязательно группе (group_task_since, 16.10.2026).

Бот пишет дату сам при включении задания. Скрипт - для заполнения прошлого
и ручной поправки: серия и недельный +5 меряют каждый день заданиями,
обязательными в тот день.

    python scripts/task_since.py quran_female.db                 # показать
    python scripts/task_since.py quran_female.db 5 j 2026-10-15  # записать
"""
import sqlite3
import sys


def main():
    path = sys.argv[1]
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE IF NOT EXISTS group_task_since(group_id INTEGER NOT NULL,"
              " task TEXT NOT NULL, since TEXT NOT NULL, PRIMARY KEY(group_id, task))")
    if len(sys.argv) == 5:
        gid, task, since = int(sys.argv[2]), sys.argv[3], sys.argv[4]
        row = c.execute("SELECT title, tasks FROM groups WHERE id=?", (gid,)).fetchone()
        if not row or task not in (row[1] or "m,r,t").split(","):
            sys.exit("нет группы %s или задания %s в её заданиях" % (gid, task))
        c.execute("INSERT OR REPLACE INTO group_task_since(group_id, task, since) VALUES(?,?,?)",
                  (gid, task, since))
        c.commit()
    for gid, title, tasks, task, since in c.execute(
            "SELECT g.id, g.title, g.tasks, s.task, s.since FROM group_task_since s"
            " JOIN groups g ON g.id=s.group_id ORDER BY g.id, s.task"):
        print(gid, title, tasks, "|", task, "с", since)


if __name__ == "__main__":
    main()
