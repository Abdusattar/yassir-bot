"""Чистка записей непредставившихся по мёртвым chat_id (14.09.2026).

Откуда берутся: группа стала супергруппой (chat_id сменился), а в
unregistered_members остались строки со старым id. Ежедневный
kick_unregistered (core/transfers.py) находит их, пытается забанить в чате,
которого больше нет («Bad Request: group chat was upgraded to a supergroup
chat»), пишет в журнал «Kicked …» и удаляет строку — по одной в день на
каждую, шум в журнале и лишние вызовы Telegram.

Скрипт удаляет разом все строки, чей chat_id не встречается в groups.
Живые группы (в том числе Тадаббур и staff) не задеваются — они в groups есть.

    python scripts/prune_dead_unregistered.py --profile female --dry-run
    python scripts/prune_dead_unregistered.py --profile female

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
    ap.add_argument("--dry-run", action="store_true", help="только показать, что будет удалено")
    args = ap.parse_args()

    os.environ["BOT_PROFILE"] = args.profile
    os.environ.setdefault("DB_PATH", str(ROOT / f"quran_{args.profile}.db"))
    sys.path.insert(0, str(ROOT))
    from core.db import db  # noqa: E402

    dead_sql = "SELECT chat_id, COUNT(*) AS n FROM unregistered_members " \
               "WHERE chat_id NOT IN (SELECT chat_id FROM groups) GROUP BY chat_id"
    print(f"база: {os.environ['DB_PATH']}")
    with db() as c:
        dead = c.execute(dead_sql).fetchall()
        if not dead:
            print("мёртвых записей нет")
            return 0
        for r in dead:
            print(f"  chat_id {r['chat_id']}: {r['n']} зап.")
        total = sum(r["n"] for r in dead)
        if args.dry_run:
            print(f"dry-run: удалил бы {total}")
            return 0
        c.execute("DELETE FROM unregistered_members "
                  "WHERE chat_id NOT IN (SELECT chat_id FROM groups)")
        left = c.execute("SELECT COUNT(*) FROM unregistered_members").fetchone()[0]
    print(f"удалено {total}, живых записей осталось {left}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
