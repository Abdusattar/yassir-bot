"""Готовность групп к таджвиду и нахву по позиции заучивания (17.09.2026).

Правило пользователя: 70% группы дошли до стр. 7 - группе открывается таджвид
(23.09.2026; было полджуза, стр. 12); 70% прошли первый джуз - нахв. Учат с
начала Аль-Бакары (стр. 2), джуз = 20 страниц: порог таджвида - указатель
заучивания на стр. 7 и дальше, нахва - на стр. 22 и дальше (core/curriculum.py
READY_PAGE). Считаются ВСЕ активные студенты группы; у кого
указателя нет (не заучивал через приложение) - «не прошёл».

Только чтение. Запускать НА СЕРВЕРЕ под окружением нужного бота:

    sudo -u stursunkul bash -c "set -a; . .env; set +a; venv/bin/python3 scripts/subject_readiness.py"
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import core.db as db                                   # noqa: E402
import core.curriculum as cur                          # noqa: E402


def main():
    db.init()
    with db.db() as c:
        groups = [dict(r) for r in c.execute(
            "SELECT id, title, tasks, group_type FROM groups WHERE active=1"
            " AND COALESCE(group_type,'relaxed') IN ('pro','relaxed') ORDER BY title")]
    print("правило включается с", cur.AUTO_OPEN_FROM)
    print("%-30s %-12s %5s %8s %8s %8s %6s %6s  %s" % (
        "группа", "задания", "всего", "с указ.", ">=пол", ">=джуз", "лекц j", "лекц n", "вывод"))
    for g in groups:
        st = cur.readiness(g["id"])
        tasks = (g["tasks"] or "").split(",")
        out = []
        for subject in ("j", "n"):
            row = cur.subject_start(g["id"], subject)
            if row:
                out.append("%s с %s" % (cur.SUBJECT_LABEL[subject], row["start_date"]))
            elif subject not in tasks and cur.is_ready(st, subject):
                out.append("пора " + cur.SUBJECT_LABEL[subject])
        print("%-30s %-12s %5d %8d %8d %8d %6d %6d  %s" % (
            (g["title"] or "")[:30], g["tasks"] or "", st["total"], st["with_pointer"], st["j"], st["n"],
            len(cur.opened_parts(g["id"], "j")), len(cur.opened_parts(g["id"], "n")), ", ".join(out)))


if __name__ == "__main__":
    main()
