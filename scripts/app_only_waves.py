"""Перевод групп на сдачу только через YassirApp волнами (16.09.2026).

Решение пользователя: берём по три группы, два дня отсчёта (утром и вечером
бот пишет в группу дату перехода), на третий день рубильник — задания и
отметка урока в чате больше не засчитываются, только приложение. Следующая
тройка стартует с задержкой в два дня, но свою дату видит с первого дня.
Подготовительной дано три дня.

Запускать НА СЕРВЕРЕ под окружением нужного бота (базы у ботов разные):

    sudo -u stursunkul bash -c "set -a; . .env; set +a; venv/bin/python3 scripts/app_only_waves.py list"
    sudo -u stursunkul bash -c "set -a; . .env; set +a; venv/bin/python3 scripts/app_only_waves.py set 'G - 12' 2026-09-18"
    sudo -u stursunkul bash -c "set -a; . .env; set +a; venv/bin/python3 scripts/app_only_waves.py clear 'G - 12'"
    ... plan  - показать готовность групп (доля сдач через приложение и кто заходил)

Порядок волн решает человек: скрипт ничего не назначает сам, он только
ставит дату конкретной группе и показывает картину.
"""
import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import core.db as db          # noqa: E402
import core.app_trail as trail  # noqa: E402
from config import PROFILE    # noqa: E402


def _find(title_part):
    hits = [g for g in db.get_all_groups()
            if title_part.lower() in (g["title"] or "").lower()]
    return hits


def cmd_list():
    rows = db.groups_with_app_only_date()
    if not rows:
        print("ни одной группы с назначенной датой")
        return
    today = db.get_date()
    for g in rows:
        state = "рубильник опущен" if g["app_only_from"] <= today else "ждёт"
        print(f"{g['title']:34} {g['app_only_from']}  {state}")


def cmd_plan(days=7):
    since = (db.get_now().date() - __import__("datetime").timedelta(days=days - 1)).isoformat()
    seen = set(trail.users_seen_since(PROFILE, hours=24 * days))
    rows = []
    for g in db.get_all_groups():
        students = db.get_students(g["id"])
        if not students:
            continue
        with db.db() as c:
            app = c.execute(
                "SELECT COUNT(*) FROM voice_submissions WHERE group_id=? AND date>=?"
                " AND hifz_page IS NOT NULL", (g["id"], since)).fetchone()[0]
            grp = c.execute(
                "SELECT COUNT(*) FROM voice_submissions WHERE group_id=? AND date>=?"
                " AND hifz_page IS NULL", (g["id"], since)).fetchone()[0]
        opened = len([s for s in students if s["phone"] in seen])
        share = app * 100 // (app + grp) if app + grp else 0
        rows.append((share, g["title"], len(students), app, grp, opened, g["app_only_from"]))
    rows.sort(reverse=True)
    print(f"{'группа':34} {'студ':>4} {'апп':>4} {'чат':>4} {'доля':>5} {'заходили':>9}  дата")
    for share, title, n, app, grp, opened, when in rows:
        print(f"{title:34} {n:4} {app:4} {grp:4} {share:4}% {opened:9}  {when or '—'}")


def cmd_set(title_part, date_str):
    hits = _find(title_part)
    if len(hits) != 1:
        print("нашёл " + str(len(hits)) + ":", [g["title"] for g in hits])
        sys.exit(1)
    g = hits[0]
    db.set_group_app_only(g["id"], date_str)
    print(f"{g['title']}: переход {date_str}")


def cmd_clear(title_part):
    hits = _find(title_part)
    if len(hits) != 1:
        print("нашёл " + str(len(hits)) + ":", [g["title"] for g in hits])
        sys.exit(1)
    g = hits[0]
    db.set_group_app_only(g["id"], None)
    print(f"{g['title']}: переход снят")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    sub.add_parser("plan")
    p_set = sub.add_parser("set")
    p_set.add_argument("group")
    p_set.add_argument("date")
    p_clear = sub.add_parser("clear")
    p_clear.add_argument("group")
    a = ap.parse_args()
    if a.cmd == "list":
        cmd_list()
    elif a.cmd == "plan":
        cmd_plan()
    elif a.cmd == "set":
        cmd_set(a.group, a.date)
    else:
        cmd_clear(a.group)


if __name__ == "__main__":
    main()
