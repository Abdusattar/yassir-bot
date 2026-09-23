"""Разово продублировать сёстрам уже прошедшее сообщение мужского Тадаббура
(23.09.2026, см. core/tadabbur_mirror.py).

Берёт сообщение из ленты мужского бота (feed_messages хранит 7 дней) по его
message_id в Тадаббуре и кладёт в общую очередь - женский бот отправит сам в
течение нескольких секунд. Форматирование (жирный, ссылки) лента не хранит -
уйдёт простым текстом.

Запускать НА СЕРВЕРЕ под окружением МУЖСКОГО бота (нужен его токен, чтобы
скачать вложение):

    sudo -u stursunkul bash -c "set -a; . .env; set +a; \\
        venv/bin/python3 scripts/tadabbur_mirror_push.py 519"
    ... --list        последние сообщения суперадминов в Тадаббуре
"""
import argparse
import asyncio
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config                                          # noqa: E402
from core.db import db, get_tadabbur_group             # noqa: E402
from core import tadabbur_mirror                       # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("message_ids", nargs="*", type=int)
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    if config.PROFILE != "male":
        sys.exit("запускать под окружением мужского бота")
    tad = get_tadabbur_group()
    with db() as c:
        if args.list or not args.message_ids:
            for r in c.execute(
                    "SELECT message_id, kind, created_at, substr(text,1,80) t FROM feed_messages"
                    " WHERE chat_id=? AND is_bot=0 ORDER BY id DESC LIMIT 15",
                    (tad["chat_id"],)):
                print(r["message_id"], r["kind"], r["created_at"], r["t"])
            return
        rows = [c.execute("SELECT * FROM feed_messages WHERE chat_id=? AND message_id=?",
                          (tad["chat_id"], mid)).fetchone() for mid in args.message_ids]
    for mid, r in zip(args.message_ids, rows):
        if not r:
            print(mid, "- нет в ленте")
            continue
        msg = {"message_id": mid}
        if r["file_id"]:
            kind = r["kind"] if r["kind"] in tadabbur_mirror.MEDIA else "document"
            msg[kind] = [{"file_id": r["file_id"]}] if kind == "photo" else {"file_id": r["file_id"]}
            msg["caption"] = r["text"]
        else:
            msg["text"] = r["text"]
        print(mid, "в очереди" if asyncio.run(tadabbur_mirror.enqueue(msg)) else "уже был в очереди")


if __name__ == "__main__":
    main()
