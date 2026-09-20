"""Сменить ссылку-приглашение подготовительной группы (20.09.2026).

Зачем: ссылки на подготовительную раздавались напрямую, и по ним в мужскую
группу заходили сёстры, а в женскую братья (разбор 19-20.09, см.
wiki/prep_group.md «Брат или сестра»). Теперь новичок должен приходить через
личку бота, где у него сначала спрашивают половину. Решение пользователя:
старые ссылки отозвать, новые раздавать только из меню бота.

Отзыв НЕОБРАТИМ для всех, у кого ссылка уже на руках, - включая тех, кого
позвали, но кто ещё не вошёл. Поэтому по умолчанию скрипт ничего не делает,
только показывает; отзыв - с ключом --send.

Оговорка про Telegram: бот может отозвать только ту ссылку, которую создал
сам. Ссылку, сделанную устазом в интерфейсе Telegram, придётся отзывать
руками (Управление группой → Пригласительные ссылки). Скрипт честно скажет,
если API откажет.

Запускать НА СЕРВЕРЕ под окружением нужного бота (базы и токены разные):

    sudo -u stursunkul bash -c "set -a; . .env; set +a; venv/bin/python3 \\
        scripts/rotate_prep_link.py"            # только показать
    ... --send                                   # отозвать и выпустить новую
"""
import argparse
import asyncio
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import core.db as db                                    # noqa: E402
from core.tg import tg_call                             # noqa: E402


def prep_groups():
    return [g for g in db.get_all_groups() if (g["group_type"] or "") == "prep"]


async def rotate(group, send):
    title = group["title"] or group["chat_id"]
    old = group["invite_link"] or ""
    print("\n%s (chat=%s)" % (title, group["chat_id"]))
    print("  сейчас: %s" % (old or "— ссылки нет —"))
    if not send:
        print("  (показ; для отзыва добавь --send)")
        return

    if old:
        res = await tg_call("revokeChatInviteLink",
                            {"chat_id": group["chat_id"], "invite_link": old})
        if res and res.get("ok"):
            print("  отозвана: старая больше не работает")
        else:
            why = (res or {}).get("description", "нет ответа")
            print("  ОТОЗВАТЬ НЕ ВЫШЛО: %s" % why)
            print("  → эту ссылку делал не бот; отзови её руками в Telegram")

    # Новую делаем именованной: в списке ссылок группы сразу видно, чья она.
    res = await tg_call("createChatInviteLink",
                        {"chat_id": group["chat_id"], "name": "YassirApp (бот)"})
    if not (res and res.get("ok")):
        print("  НОВУЮ СОЗДАТЬ НЕ ВЫШЛО: %s" % (res or {}).get("description", "нет ответа"))
        return
    link = res["result"]["invite_link"]
    db.set_group_invite_link(group["id"], link)
    print("  новая:  %s" % link)


async def main_async(send):
    groups = prep_groups()
    if not groups:
        print("подготовительной группы в этой базе нет")
        return
    for g in groups:
        await rotate(g, send)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true", help="отозвать и выпустить новую")
    args = ap.parse_args()
    print("база: %s" % db.DB)
    asyncio.run(main_async(args.send))


if __name__ == "__main__":
    main()
