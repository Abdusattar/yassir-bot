"""Записать человека в подготовительную без входа в её Telegram-чат.

Обычно в prep записывает бот, когда человек вступает в чат по ссылке
(core/transfers.py:handle_known_user_group_join → add_student). Но с 19.09
подготовительная живёт в приложении (app_only_from), а у человека может не
быть Telegram вовсе (12.10.2026: Саламат сменил телефон, Telegram не пускает,
в приложение входит по почте) — тогда вход в чат так и не случится.

Скрипт делает ровно то же, что обычный вход известного человека в prep,
теми же функциями core/db.py: add_student (активна, свежая дата входа —
14 дней считаются с сегодня). Онбординга нет — он только для новичков.
Метка «вернуться через prep» и Тадаббур не трогаются: их снимает выпуск.
Активного студента pro/relaxed не записывает — бот такого из prep кикает.

    python scripts/enter_prep.py --phone 581555264
    python scripts/enter_prep.py --phone 581555264 --apply

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
    parser.add_argument("--apply", action="store_true", help="выполнить, а не показать")
    args = parser.parse_args()

    db.init()
    user = db.find_user_by_phone(args.phone)
    if not user:
        raise SystemExit("нет такого пользователя: " + args.phone)
    prep = db.get_prep_group()
    if not prep:
        raise SystemExit("подготовительной группы нет")
    active = db.get_learning_group(args.phone)
    if active:
        raise SystemExit("%s активен в «%s» — в prep не записываю" % (user["name"], active["title"]))

    print("%s (%s) → %s" % (user["name"], args.phone, prep["title"]))
    if db.find_by_phone(args.phone, prep["id"]):
        print("  уже в подготовительной, делать нечего")
        return
    print("  · добавить студентом, дата входа — сегодня (%s)" % db.get_date())
    print("  · метка «вернуться через prep»: %s (остаётся до выпуска)"
          % ("есть" if db.is_pending_prep_return(args.phone) else "нет"))
    if not args.apply:
        print("\nэто предпросмотр; повтори с --apply, чтобы выполнить")
        return

    db.add_student(user["name"], prep["id"], args.phone)
    print("\nготово")


if __name__ == "__main__":
    main()
