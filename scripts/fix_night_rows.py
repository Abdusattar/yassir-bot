"""Перенести на верный день зачёты, записанные до трёх ночи (20.09.2026).

До введения учебного дня (core/db.py: STUDY_DAY_END_HOUR) зачёт писался на
календарную дату, и сдача после полуночи уезжала в следующий день: прошедший
оставался пустым и считался пропуском. Правка в коде работает только вперёд,
а старые строки лежат как лежали.

Решение пользователя: править не всем подряд, а только тем, кто из-за этого
у порога. Пороги живут в core/transfers.py: у pro предупреждение при пяти
пропусках и перевод при десяти, у relaxed - пятнадцать и двадцать. Поэтому по
умолчанию берём только pro-группы.

Что делает со строкой, записанной в 00:00-02:59 по Бишкеку:
  - если на предыдущем дне такого зачёта нет - переносит (date = date - 1);
  - если есть - удаляет: тот день уже закрыт этим же заданием, перенос лишь
    создал бы дубль (UNIQUE student_id+group_id+date+category+subcategory).

По умолчанию НИЧЕГО не меняет - только показывает. Перед --send делает копию
базы рядом с ней. Запускать НА СЕРВЕРЕ под окружением нужного бота:

    sudo -u stursunkul bash -c "set -a; . .env; set +a; venv/bin/python3 \\
        scripts/fix_night_rows.py --since 2026-09-01"
    ... --types pro,relaxed     расширить круг групп
    ... --send                  перенести на самом деле
"""
import argparse
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import core.db as db                                    # noqa: E402

NIGHT_HOURS = 3          # то же, что STUDY_DAY_END_HOUR
TZ_SHIFT = "+6 hours"    # created_at хранится в UTC, Бишкек = +6


def night_rows(c, since, types):
    marks = ",".join("?" * len(types))
    return c.execute(
        "SELECT se.id, se.student_id, u.name, se.group_id, g.title, g.group_type,"
        "       se.date, se.subcategory,"
        "       datetime(se.created_at, '%s') AS local"
        "  FROM score_events se"
        "  JOIN users u ON u.id=se.student_id"
        "  JOIN groups g ON g.id=se.group_id"
        " WHERE se.category='task' AND se.date>=?"
        "   AND g.group_type IN (%s)"
        "   AND CAST(strftime('%%H', datetime(se.created_at, '%s')) AS INT) < ?"
        " ORDER BY u.name, se.date" % (TZ_SHIFT, marks, TZ_SHIFT),
        (since, *types, NIGHT_HOURS)).fetchall()


def plan(c, rows):
    """(перенести, удалить-как-дубль) — решение по каждой строке."""
    move, drop = [], []
    for r in rows:
        clash = c.execute(
            "SELECT 1 FROM score_events WHERE student_id=? AND group_id=?"
            "   AND date=date(?, '-1 day') AND category='task' AND subcategory=?",
            (r["student_id"], r["group_id"], r["date"], r["subcategory"])).fetchone()
        (drop if clash else move).append(r)
    return move, drop


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-09-01")
    ap.add_argument("--types", default="pro", help="типы групп через запятую")
    ap.add_argument("--send", action="store_true")
    args = ap.parse_args()
    types = [t.strip() for t in args.types.split(",") if t.strip()]

    print("база: %s · группы: %s · с %s" % (db.DB, ", ".join(types), args.since))
    with db.db() as c:
        rows = night_rows(c, args.since, types)
        move, drop = plan(c, rows)

    if not rows:
        print("ночных записей нет")
        return

    print("\nперенести на день назад (%d):" % len(move))
    for r in move:
        print("  %-18s %-8s %s → %s   %s  (%s)" % (
            r["name"][:18], r["title"], r["date"],
            (db.datetime.strptime(r["date"], "%Y-%m-%d") - db.timedelta(days=1)).date(),
            r["subcategory"], r["local"][11:16]))
    print("\nудалить как дубль (%d): тот день уже закрыт этим же заданием" % len(drop))
    for r in drop:
        print("  %-18s %-8s %s  %s  (%s)" % (
            r["name"][:18], r["title"], r["date"], r["subcategory"], r["local"][11:16]))

    if not args.send:
        print("\nНЕ применено: это просмотр. Для правки добавь --send")
        return

    backup = "%s.before-night-fix" % db.DB
    shutil.copyfile(db.DB, backup)
    print("\nкопия базы: %s" % backup)

    with db.db() as c:
        for r in move:
            c.execute("UPDATE score_events SET date=date(date, '-1 day') WHERE id=?", (r["id"],))
        for r in drop:
            c.execute("DELETE FROM score_events WHERE id=?", (r["id"],))
    print("перенесено %d, удалено дублей %d" % (len(move), len(drop)))


if __name__ == "__main__":
    main()
