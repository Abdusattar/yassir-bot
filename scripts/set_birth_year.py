"""Год рождения от устаза/админа, запертый от правки (16.09.2026).

Зачем: несовершеннолетним «повторение» засчитывается только записью чтения
(см. core/db.py: revision_record_required). Признак берётся из года рождения,
и ставить его для детей должен взрослый, а не сам ребёнок - иначе одна цифра
в настройках снимает требование. Поставленный здесь год виден в настройках
приложения, но не редактируется («указан устазом»).

Запускать НА СЕРВЕРЕ под окружением нужного бота (базы у ботов разные):

    sudo -u stursunkul bash -c "set -a; . .env; set +a; venv/bin/python3 scripts/set_birth_year.py list"
    sudo -u stursunkul bash -c "set -a; . .env; set +a; venv/bin/python3 scripts/set_birth_year.py set 'Имя' 2011 --group 'N-1'"
    sudo -u stursunkul bash -c "set -a; . .env; set +a; venv/bin/python3 scripts/set_birth_year.py clear 'Имя' --group 'N-1'"

  list              - у кого стоит запертый год и нужна ли запись сегодня
  set ИМЯ ГОД       - поставить и запереть (--group сужает поиск по названию группы)
  clear ИМЯ         - снять год и замок

Имя ищется без учёта регистра по вхождению среди активных студентов; если
подходит больше одного - скрипт перечисляет и ничего не меняет.
"""
import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import core.db as db  # noqa: E402


def _find(name, group_part=None):
    hits = []
    for g in db.get_all_groups():
        if group_part and group_part.lower() not in (g["title"] or "").lower():
            continue
        for st in db.get_students(g["id"]):
            if name.lower() in (st["name"] or "").lower():
                hits.append((st, g))
    return hits


def cmd_list():
    with db.db() as c:
        rows = c.execute(
            "SELECT u.name, u.phone, u.survey_birth_year, g.title"
            " FROM users u LEFT JOIN groups g ON g.id = u.group_id"
            " WHERE u.birth_year_locked = 1 ORDER BY g.title, u.name"
        ).fetchall()
    if not rows:
        print("запертых годов нет")
        return
    for r in rows:
        need = db.revision_record_required(r["phone"])
        print(f"{r['title'] or '—':20} {r['name']:25} {r['survey_birth_year']}  "
              f"{'запись нужна' if need else 'взрослый по году'}")


def cmd_set(name, year, group_part):
    hits = _find(name, group_part)
    if len(hits) != 1:
        print("нашёл " + str(len(hits)) + ":", [(s["name"], g["title"]) for s, g in hits])
        sys.exit(1)
    st, g = hits[0]
    if not st.get("phone"):
        sys.exit(f"{st['name']}: нет Telegram ID (phone), профиль не найти")
    db.set_student_birth_year(st["phone"], year)
    print(f"{st['name']} ({g['title']}): год {year}, заперт; запись нужна: "
          f"{db.revision_record_required(st['phone'])}")


def cmd_clear(name, group_part):
    hits = _find(name, group_part)
    if len(hits) != 1:
        print("нашёл " + str(len(hits)) + ":", [(s["name"], g["title"]) for s, g in hits])
        sys.exit(1)
    st, g = hits[0]
    db.set_student_birth_year(st["phone"], None)
    print(f"{st['name']} ({g['title']}): год и замок сняты")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    p_set = sub.add_parser("set")
    p_set.add_argument("name")
    p_set.add_argument("year", type=int)
    p_set.add_argument("--group")
    p_clear = sub.add_parser("clear")
    p_clear.add_argument("name")
    p_clear.add_argument("--group")
    a = ap.parse_args()
    if a.cmd == "list":
        cmd_list()
    elif a.cmd == "set":
        cmd_set(a.name, a.year, a.group)
    else:
        cmd_clear(a.name, a.group)


if __name__ == "__main__":
    main()
