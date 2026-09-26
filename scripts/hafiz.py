"""Отметка «хафиз» (26.09.2026, решение пользователя).

Хафизу заучивание (m) не обязательно: полный день, стрик, напоминания,
«Мой день» считаются без него (core/db.py: student_tasks). Сдаст - балл
засчитан как обычно. На кнопке 🔁 вопрос «Вы сделали сегодняшнее
повторение?» вместо «с начала суры Аль-Бакара». Отметка у человека, не у
группы - переезжает с ним.

    python scripts/hafiz.py --profile male                   # кто отмечен
    python scripts/hafiz.py --profile male --user-id 14      # отметить
    python scripts/hafiz.py --profile male --user-id 14 --undo

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
    ap.add_argument("--user-id", type=int)
    ap.add_argument("--undo", action="store_true")
    a = ap.parse_args()

    os.environ["BOT_PROFILE"] = a.profile
    os.environ.setdefault("DB_PATH", str(ROOT / ("quran_%s.db" % a.profile)))
    sys.path.insert(0, str(ROOT))
    from core.db import db, init, set_hafiz   # noqa: E402

    init()   # колонка is_hafiz появляется миграцией
    if a.user_id:
        with db() as c:
            u = c.execute("SELECT id, name FROM users WHERE id=?", (a.user_id,)).fetchone()
        if not u:
            print("нет пользователя %s" % a.user_id)
            return 1
        set_hafiz(u["id"], not a.undo)
        print(("снята отметка: " if a.undo else "хафиз: ") + "%s (id %s)" % (u["name"], u["id"]))

    with db() as c:
        rows = c.execute("""
            SELECT u.id, u.name, GROUP_CONCAT(g.title, ', ') AS groups
            FROM users u
            LEFT JOIN user_groups ug ON ug.user_id=u.id AND ug.active=1 AND ug.role='student'
            LEFT JOIN groups g ON g.id=ug.group_id
            WHERE u.is_hafiz=1 GROUP BY u.id ORDER BY u.name
        """).fetchall()
    print("хафизы (%s): %d" % (a.profile, len(rows)))
    for r in rows:
        print("  %s (id %s) - %s" % (r["name"], r["id"], r["groups"] or "без группы"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
