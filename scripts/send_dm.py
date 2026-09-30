"""Личное сообщение одному человеку от имени бота (30.09.2026).

Зачем: после разбора жалобы сказать самому человеку, что было и что
исправлено (первый случай - Азиля, Сальмина, Эрлан и Умар устаз). Раньше для
этого писали одноразовый код прямо на сервере.

По умолчанию НИЧЕГО не отправляет - показывает, кому и что уйдёт. Отправка -
с ключом --send. Запускать НА СЕРВЕРЕ под окружением нужного бота (у мужского
и женского свои токены и базы):

    sudo -u stursunkul bash -c "set -a; . .env.female; set +a; \
        venv/bin/python3 scripts/send_dm.py --user-id 633 --text-file /tmp/dm.txt"
    ... --send                 отправить на самом деле

Шлём только тем, кто нажимал «Старт» у бота (dm_ok): остальным Telegram
всё равно не даст написать первым.
"""
import argparse
import asyncio
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.db import db                                 # noqa: E402
from core.tg import send_message                       # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user-id", type=int, required=True, help="users.id в базе этого бота")
    ap.add_argument("--text-file", required=True)
    ap.add_argument("--send", action="store_true")
    a = ap.parse_args()

    text = pathlib.Path(a.text_file).read_text(encoding="utf-8").strip()
    with db() as c:
        u = c.execute("SELECT id, name, phone, dm_ok FROM users WHERE id=?", (a.user_id,)).fetchone()
    if not u:
        print("нет пользователя %s в этой базе" % a.user_id)
        return 1
    print("кому: %s (%s), личка открыта: %s" % (u["name"], u["phone"], "да" if u["dm_ok"] else "НЕТ"))
    print("-" * 40)
    print(text)
    print("-" * 40)
    if not u["dm_ok"]:
        print("не отправляю: человек не нажимал «Старт»")
        return 1
    if not a.send:
        print("проверка - без --send ничего не ушло")
        return 0
    res = asyncio.run(send_message(u["phone"], text))
    print("отправлено" if res else "НЕ отправлено: %r" % (res,))
    return 0 if res else 1


if __name__ == "__main__":
    sys.exit(main())
