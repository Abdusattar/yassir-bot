"""Перенос группы на новый chat_id вручную (14.09.2026).

Зачем: когда группа Telegram становится супергруппой, chat_id меняется, и
бот подхватывает это сам — по служебному сообщению migrate_to_chat_id в
старый чат (bot.py). Но если бота в момент преобразования в группе НЕ БЫЛО
(случай женской подготовительной 12–13.09.2026: бот там числился «left»),
сообщение ему не приходит, и в базе остаётся мёртвый chat_id: группа молча
отваливается — ни приветствий, ни отсчёта дней, ни утренних рассылок
(«Bad Request: group chat was upgraded to a supergroup chat» в журнале).

Скрипт делает ровно то же, что делает сам бот при миграции —
core.db.update_group_chat_id — плюс, по желанию, записывает новую ссылку
приглашения (у супергруппы она своя; старую Telegram не переносит).

    python scripts/migrate_group_chat.py -5587079248 -1003503925527 \
        --profile female --link https://t.me/+XXXX

Идемпотентен: если строка с новым chat_id уже есть — ничего не меняет.
Запускать на сервере из корня репозитория от владельца базы (stursunkul).
"""
import argparse
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("old_chat_id", help="chat_id, который лежит в базе сейчас")
    ap.add_argument("new_chat_id", help="chat_id супергруппы (-100…)")
    ap.add_argument("--profile", default="male", choices=["male", "female"])
    ap.add_argument("--link", help="новая ссылка приглашения (getChat.invite_link)")
    ap.add_argument("--dry-run", action="store_true", help="только показать, что будет сделано")
    args = ap.parse_args()

    os.environ["BOT_PROFILE"] = args.profile
    os.environ.setdefault("DB_PATH", str(ROOT / f"quran_{args.profile}.db"))
    sys.path.insert(0, str(ROOT))
    from core.db import get_group, set_group_invite_link, update_group_chat_id  # noqa: E402

    old = get_group(args.old_chat_id)
    new = get_group(args.new_chat_id)
    print(f"база: {os.environ['DB_PATH']}")
    print(f"старый {args.old_chat_id}: {dict(old) if old else '— нет такой группы'}")
    print(f"новый  {args.new_chat_id}: {dict(new) if new else '— свободен'}")

    if not old and not new:
        print("ни старого, ни нового chat_id в базе нет — переносить нечего")
        return 1
    if args.dry_run:
        print("dry-run: изменений нет")
        return 0

    if new:
        print("перенос уже состоялся — chat_id не трогаю")
    else:
        moved = update_group_chat_id(args.old_chat_id, args.new_chat_id)
        print("перенос chat_id:", "готово" if moved else "пропущен")

    group = get_group(args.new_chat_id)
    if args.link:
        set_group_invite_link(group["id"], args.link)
        print("ссылка приглашения записана")

    group = get_group(args.new_chat_id)
    print(f"итог: id={group['id']} «{group['title']}» chat_id={group['chat_id']} "
          f"type={group['group_type']} link={group['invite_link'] or '—'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
