"""Готовность групп к таджвиду и нахву по позиции заучивания (17.09.2026).

Правило пользователя: 70% группы прошли полджуза - группе открывается таджвид;
70% прошли первый джуз - нахв. Учат с начала Аль-Бакары (стр. 2), джуз = 20
страниц: полджуза пройдено, когда указатель заучивания на стр. 12 и дальше,
джуз - на стр. 22 и дальше. Считаются ВСЕ активные студенты группы; у кого
указателя нет (не заучивал через приложение) - «не прошёл».

Только чтение. Запускать НА СЕРВЕРЕ под окружением нужного бота:

    sudo -u stursunkul bash -c "set -a; . .env; set +a; venv/bin/python3 scripts/subject_readiness.py"
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import core.db as db                                   # noqa: E402
from core.mushaf_words import get_hifz_pointer         # noqa: E402

HALF_JUZ_PAGE = 12
JUZ_PAGE = 22
SHARE = 0.7


def main():
    db.init()
    with db.db() as c:
        groups = [dict(r) for r in c.execute(
            "SELECT id, title, tasks, group_type FROM groups WHERE active=1"
            " AND COALESCE(group_type,'relaxed') IN ('pro','relaxed') ORDER BY title")]
    print("%-30s %-12s %5s %8s %8s %8s  %s" % ("группа", "задания", "всего", "с указ.", ">=пол", ">=джуз", "вывод"))
    for g in groups:
        students = [s for s in db.get_students(g["id"]) if s["phone"]]
        pages = []
        for s in students:
            p = get_hifz_pointer(s["phone"])
            if p and p.get("page"):
                pages.append(int(p["page"]))
        n = len(students)
        half = sum(1 for p in pages if p >= HALF_JUZ_PAGE)
        juz = sum(1 for p in pages if p >= JUZ_PAGE)
        tasks = (g["tasks"] or "").split(",")
        out = []
        if n and half / n >= SHARE and "j" not in tasks:
            out.append("пора таджвид")
        if n and juz / n >= SHARE and "n" not in tasks:
            out.append("пора нахв")
        print("%-30s %-12s %5d %8d %8d %8d  %s" % (
            (g["title"] or "")[:30], g["tasks"] or "", n, len(pages), half, juz, ", ".join(out)))


if __name__ == "__main__":
    main()
