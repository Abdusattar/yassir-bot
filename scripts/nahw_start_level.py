"""Стартовый уровень группы в тренажёре нахва (17.09.2026).

Зачем: навыки открываются шаг за шагом - урок опубликован и предыдущий навык
освоен. Но группа может уйти вперёд на живых лекциях (N-1): ей первые навыки
открываются сразу, без письменных уроков. Уровень определяем по сдачам самого
знающего студента группы (решение пользователя 17.09.2026).

Запускать НА СЕРВЕРЕ под окружением нужного бота (базы у ботов разные):

    sudo -u stursunkul bash -c "set -a; . .env; set +a; venv/bin/python3 scripts/nahw_start_level.py list"
    sudo -u stursunkul bash -c "set -a; . .env; set +a; venv/bin/python3 scripts/nahw_start_level.py set 'N-1' 7"
    sudo -u stursunkul bash -c "set -a; . .env; set +a; venv/bin/python3 scripts/nahw_start_level.py set 'N-1' 0"
"""
import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import core.db as db                 # noqa: E402
import core.nahw_trainer as nt       # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    st = sub.add_parser("set")
    st.add_argument("group")
    st.add_argument("passed", type=int)
    args = ap.parse_args()
    db.init()
    print("навыки по порядку:", ", ".join("%d %s" % (i + 1, s["title"]) for i, s in enumerate(nt.SKILLS)))
    with db.db() as c:
        groups = [dict(r) for r in c.execute("SELECT id, title, tasks FROM groups WHERE active=1")]
    if args.cmd == "list":
        for g in groups:
            if "n" in (g["tasks"] or "").split(","):
                print("%-34s пройдено на лекциях: %d" % (g["title"], nt.group_passed(g["id"])))
        return
    found = [g for g in groups if g["title"] == args.group]
    if len(found) != 1 or not 0 <= args.passed <= len(nt.SKILLS):
        raise SystemExit("группа не найдена однозначно или уровень вне 0..%d" % len(nt.SKILLS))
    nt.set_group_passed(found[0]["id"], args.passed)
    print("%s: пройдено на лекциях %d" % (args.group, args.passed))


if __name__ == "__main__":
    main()
