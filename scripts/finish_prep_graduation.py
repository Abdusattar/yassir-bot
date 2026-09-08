"""Дооформить выпуск из подготовительной, когда автоматика его не провела.

Обычно выпуск делает core/prep.py:announce_prep_graduate_arrival — она ловит
первый вход выпускника в учебную группу и снимает метку «должен вернуться
через prep», убирает из подготовительной и из Тадаббура. Но ей нужен именно
этот момент входа, а он бывает пропущен (08.09.2026: Имран — устаз группы
«Отбор.» и студент N-1; вход устаза бот тогда не обрабатывал вовсе, а сам
Имран через минуту вышел из подготовительной — и выпуск повис в никуда).

Скрипт делает ровно то же, что сделала бы announce_prep_graduate_arrival,
через те же функции core/db.py — и ничего сверх: никаких правок таблиц
руками. Идемпотентен: повторный запуск ничего не ломает.

    python scripts/finish_prep_graduation.py --phone 5818654390 --group N-1
    python scripts/finish_prep_graduation.py --phone ... --group ... --apply

Без --apply только показывает, что будет сделано.
"""
import argparse
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
os.environ.setdefault("TELEGRAM_TOKEN", "dev")

import core.db as db  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phone", required=True, help="Telegram ID студента")
    parser.add_argument("--group", required=True, help="название учебной группы (N-1)")
    parser.add_argument("--apply", action="store_true", help="выполнить, а не показать")
    args = parser.parse_args()

    db.init()
    user = db.find_user_by_phone(args.phone)
    if not user:
        raise SystemExit("нет такого пользователя: " + args.phone)
    group = db.get_group_by_title(args.group)
    if not group:
        raise SystemExit("нет такой группы: " + args.group)

    plan = []
    if db.is_pending_prep_return(args.phone):
        plan.append("снять метку pending_prep_return")
    if not db.find_by_phone(args.phone, group["id"]):
        plan.append("добавить студентом в «%s»" % group["title"])
    tadabbur = db.get_tadabbur_group()
    if tadabbur and db.find_by_phone(args.phone, tadabbur["id"]):
        plan.append("убрать из Тадаббура")
    # Подготовительная: выпускник в ней больше не числится.
    for g in db.get_all_groups():
        if (g["group_type"] or "") == "prep" and db.find_by_phone(args.phone, g["id"]):
            plan.append("деактивировать в подготовительной «%s»" % g["title"])

    print("%s (%s) → %s" % (user["name"], args.phone, group["title"]))
    if not plan:
        print("  всё уже в порядке, делать нечего")
        return
    for step in plan:
        print("  · " + step)
    if not args.apply:
        print("\nэто предпросмотр; повтори с --apply, чтобы выполнить")
        return

    db.clear_pending_prep_return(args.phone)
    db.add_student(user["name"], group["id"], args.phone)
    if tadabbur:
        db.deactivate_student(user["id"], tadabbur["id"])
    for g in db.get_all_groups():
        if (g["group_type"] or "") == "prep":
            db.deactivate_student(user["id"], g["id"])
    print("\nготово")


if __name__ == "__main__":
    main()
