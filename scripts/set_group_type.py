"""Сменить тип групп без сообщения в чат (02.10.2026).

`/settype` в группе сразу пишет туда «✅ Тип группы: …» сухой строкой. Когда
перевод сопровождается своим объявлением (scripts/announce.py), эта строка
лишняя. Скрипт меняет тип тем же db.update_group_type и молчит.

По умолчанию НИЧЕГО не меняет - только показывает. Применить - с --apply.
Запускать на сервере под окружением нужного бота:

    sudo -u stursunkul bash -c "set -a; . .env.female; set +a; venv/bin/python3 \
        scripts/set_group_type.py --type pro --groups 'Группа 1📚устаза Зейнеб,...'"
"""
import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config                                          # noqa: E402
import core.db as db                                   # noqa: E402

TYPES = ("pro", "relaxed", "tadabbur", "prep", "staff")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--type", required=True, choices=TYPES)
    ap.add_argument("--groups", required=True, help="названия через запятую (точное совпадение)")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    want = [t.strip() for t in a.groups.split(",") if t.strip()]
    found = [g for g in db.get_all_groups() if (g["title"] or "").strip() in want]
    missing = set(want) - {(g["title"] or "").strip() for g in found}
    if missing:
        raise SystemExit("нет таких групп: " + ", ".join(sorted(missing)))
    print("Бот:", config.PROFILE)
    for g in found:
        print(f"  {g['title']}: {g['group_type']} → {a.type}")
        if a.apply:
            db.update_group_type(g["chat_id"], a.type)
    print("Применено." if a.apply else "Ничего не изменено (нужен --apply).")


if __name__ == "__main__":
    main()
