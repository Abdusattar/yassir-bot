"""Поправить отметки онлайн-урока задним числом (14.09.2026).

Зачем: до 14.09 бот засчитывал «у» раз в календарную неделю и молча
отбрасывал вторую отметку. 13.09 во 2 группе устаза Асмы так остались без
урока сёстры, у которых урок прошлой недели был отмечен в понедельник 07.09,
а у двоих повторное «у» после полуночи засчиталось уже 14.09 - датой
следующей недели. Скрипт возвращает такие случаи через обычные функции
базы, без ручного SQL.

    python scripts/fix_lesson_attendance.py --profile female --group-id 7 \\
        --credit 369:2026-09-13 --credit 395:2026-09-13 \\
        --move 467:2026-09-14:2026-09-13 --move 362:2026-09-14:2026-09-13 --dry-run

--credit SID:ДАТА          засчитать урок на эту дату (+5, как «у»)
--move SID:ОТКУДА:КУДА     перенести уже засчитанную отметку на другой день

Идемпотентен: повторный --credit ничего не добавит (UNIQUE на день), --move
не сработает, если отметка уже стоит на целевом дне. Правило «две в неделю»
здесь сознательно не проверяется: это ручное исправление после разбора.
Запускать на сервере из корня репозитория от владельца базы (stursunkul).
"""
import argparse
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--profile", default="male", choices=["male", "female"])
    ap.add_argument("--group-id", type=int, required=True)
    ap.add_argument("--credit", action="append", default=[], metavar="SID:DATE")
    ap.add_argument("--move", action="append", default=[], metavar="SID:FROM:TO")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    os.environ["BOT_PROFILE"] = args.profile
    os.environ.setdefault("DB_PATH", str(ROOT / f"quran_{args.profile}.db"))
    sys.path.insert(0, str(ROOT))
    from core.db import add_bonus, get_lesson_dates, get_students, move_lesson_attendance  # noqa: E402

    gid = args.group_id
    students = {s["id"]: s["name"] for s in get_students(gid)}
    plan = []
    for item in args.credit:
        sid, date = item.split(":")
        plan.append(("credit", int(sid), date, None))
    for item in args.move:
        sid, src, dst = item.split(":")
        plan.append(("move", int(sid), src, dst))

    print(f"база: {os.environ['DB_PATH']}  группа id={gid}")
    for kind, sid, a, b in plan:
        if sid not in students:
            print(f"  ✗ студент {sid} не состоит в группе {gid} — пропуск")
            continue
        before = get_lesson_dates(sid, gid, a[:7])
        what = f"засчитать {a}" if kind == "credit" else f"перенести {a} → {b}"
        if args.dry_run:
            print(f"  · {students[sid]} ({sid}): {what}; сейчас {before}")
            continue
        if kind == "credit":
            add_bonus(sid, gid, a, 5, "attendance", "online")
        else:
            move_lesson_attendance(sid, gid, a, b)
        print(f"  ✓ {students[sid]} ({sid}): {what}; было {before}, стало {get_lesson_dates(sid, gid, a[:7])}")
    if args.dry_run:
        print("dry-run: ничего не изменено")
    return 0


if __name__ == "__main__":
    sys.exit(main())
