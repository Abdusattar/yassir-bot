"""Объявление в группы от имени бота - с пометкой «важное» (17.09.2026).

Зачем: объявления, которые пишем сами (не по расписанию), раньше уходили
обычным сообщением и тонули в чате. Через этот скрипт объявление попадает на
доску важного в YassirApp (core/feed.py) и висит там до своей даты.

По умолчанию НИЧЕГО не отправляет - только показывает, куда и что уйдёт.
Отправка - с ключом --send. Запускать НА СЕРВЕРЕ под окружением нужного бота:

    sudo -u stursunkul bash -c "set -a; . .env; set +a; venv/bin/python3 scripts/announce.py \
        --text-file /tmp/ann.txt --groups all --until 2026-09-25"
    ... --groups "N-1,G-12"         по названиям (точное совпадение)
    ... --groups task:j              группам, где есть задание (j, n, h...)
    ... --type task                  «Новое задание» вместо «Объявление»
    ... --send                       отправить на самом деле
"""
import argparse
import asyncio
import pathlib
import sys
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import core.db as db                                   # noqa: E402
from core.feed import important                        # noqa: E402
from core.db import bot_leads_group                   # noqa: E402
from core.tg import send_message                       # noqa: E402


def pick_groups(spec):
    groups = [g for g in db.get_all_groups()
              if bot_leads_group(g["group_type"] or "relaxed")]
    if spec == "all":
        return groups
    if spec.startswith("task:"):
        key = spec[5:].strip()
        return [g for g in groups if key in [t.strip() for t in (g["tasks"] or "").split(",")]]
    # Группу, названную поимённо, ищем среди ВСЕХ, а не только учебных
    # (20.09.2026): общие правила джамаата объявляют в Тадаббуре, а его бот
    # как учебную группу не ведёт - и скрипт отвечал «нет такой группы».
    # Для all и task: фильтр остаётся: массовая рассылка в служебные чаты
    # не нужна.
    want = [t.strip() for t in spec.split(",") if t.strip()]
    found = [g for g in db.get_all_groups() if (g["title"] or "").strip() in want]
    missing = set(want) - {(g["title"] or "").strip() for g in found}
    if missing:
        raise SystemExit("нет таких групп: " + ", ".join(sorted(missing)))
    return found


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text-file", required=True)
    ap.add_argument("--groups", required=True)
    ap.add_argument("--until", default=None, help="дата ISO, до которой висит на доске (по умолчанию 2 дня)")
    ap.add_argument("--type", default="announce", choices=("announce", "task"))
    ap.add_argument("--title", default=None, help="строка для доски (по умолчанию первая строка текста)")
    ap.add_argument("--send", action="store_true")
    args = ap.parse_args()
    if args.until:
        date.fromisoformat(args.until)
    text = pathlib.Path(args.text_file).read_text(encoding="utf-8").strip()
    if not text:
        raise SystemExit("пустой текст")
    db.init()
    groups = pick_groups(args.groups)
    print("тип: %s · висит до: %s · групп: %d" % (args.type, args.until or "+2 дня", len(groups)))
    for g in groups:
        print("  -", g["title"])
    print("-" * 40)
    print(text)
    print("-" * 40)
    if not args.send:
        print("НЕ отправлено: это просмотр. Для отправки добавь --send")
        return
    for g in groups:
        with important(args.type, until=args.until, title=args.title):
            res = await send_message(g["chat_id"], text)
        print("  %s: %s" % (g["title"], "ок" if res and res.get("ok") else "НЕ ДОШЛО"))
        await asyncio.sleep(0.4)


if __name__ == "__main__":
    asyncio.run(main())
