"""Заполнить ссылки-приглашения учебных групп силами самого бота (14.09.2026).

Зачем: выпускник подготовительной направляется в наименее заполненную
группу, У КОТОРОЙ ЕСТЬ invite_link (core/db.py get_best_group_for_transfer);
группа без ссылки для бота не существует. У сестёр 14.09 ссылка была у 1 из
10 групп — все выпускницы уходили бы в одну и ту же группу. Ссылку ставит
устаз командой /setlink, но бот и сам админ с правом приглашать, поэтому
берёт её у Telegram напрямую (решение пользователя 14.09).

Что делает: для каждой активной группы выбранных типов без ссылки зовёт
createChatInviteLink (новая именованная ссылка, существующие ссылки устазов
НЕ отзываются — в отличие от exportChatInviteLink) и записывает её в базу
через core.db.set_group_invite_link. Группы, где ссылка уже есть, не трогает.

    python scripts/fill_invite_links.py --profile female --dry-run
    python scripts/fill_invite_links.py --profile female
    python scripts/fill_invite_links.py --profile male --exclude 21,22
        (21 «Отбор.», 22 «Группа для детей» — специальные, выпускников туда
        не направляем; решение пользователя 14.09)

Запускать на сервере из корня репозитория от владельца базы (stursunkul):
токен берётся из .env / .env.female рядом с базой.
"""
import argparse
import json
import os
import pathlib
import re
import sys
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _load_env(profile):
    """Подхватить .env профиля, не перебивая уже выставленные переменные."""
    path = ROOT / (".env" if profile == "male" else ".env.female")
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$", line)
        if m and m.group(1) not in os.environ:
            os.environ[m.group(1)] = m.group(2).strip("\"'")


def _tg(token, method, **params):
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request("https://api.telegram.org/bot%s/%s" % (token, method), data=data)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--profile", default="male", choices=["male", "female"])
    ap.add_argument("--types", default="pro,relaxed",
                    help="типы групп через запятую (по умолчанию pro,relaxed)")
    ap.add_argument("--exclude", default="",
                    help="id групп через запятую, которые не трогать (специальные: отбор, дети)")
    ap.add_argument("--dry-run", action="store_true", help="только показать, где ссылки нет")
    args = ap.parse_args()
    exclude = {int(x) for x in args.exclude.split(",") if x.strip()}

    os.environ["BOT_PROFILE"] = args.profile
    os.environ.setdefault("DB_PATH", str(ROOT / f"quran_{args.profile}.db"))
    _load_env(args.profile)
    sys.path.insert(0, str(ROOT))
    from config import TELEGRAM_TOKEN  # noqa: E402
    from core.db import db, set_group_invite_link  # noqa: E402

    if not TELEGRAM_TOKEN:
        print("нет токена бота — проверь .env профиля")
        return 1
    me = _tg(TELEGRAM_TOKEN, "getMe")["result"]
    types = [t.strip() for t in args.types.split(",") if t.strip()]
    print(f"база: {os.environ['DB_PATH']}  бот: @{me.get('username')}  типы: {', '.join(types)}")

    with db() as c:
        rows = c.execute(
            "SELECT id, chat_id, title, group_type, invite_link FROM groups "
            "WHERE active=1 AND group_type IN (%s) ORDER BY id" % ",".join("?" * len(types)),
            types,
        ).fetchall()

    missing = [r for r in rows if not (r["invite_link"] or "").strip()]
    skipped = [r for r in missing if r["id"] in exclude]
    missing = [r for r in missing if r["id"] not in exclude]
    print(f"учебных групп: {len(rows)}, без ссылки: {len(missing) + len(skipped)}, "
          f"исключено: {len(skipped)}")
    for r in skipped:
        print(f"  – [{r['id']}] «{r['title']}» — исключена, ссылку не завожу")
    if not missing:
        return 0
    for r in missing:
        print(f"  [{r['id']}] «{r['title']}» ({r['group_type']}) chat_id={r['chat_id']}")
    if args.dry_run:
        print("dry-run: ничего не создано")
        return 0

    done = failed = 0
    for r in missing:
        try:
            resp = _tg(TELEGRAM_TOKEN, "createChatInviteLink",
                       chat_id=r["chat_id"], name="Yassir bot")
        except Exception as e:  # HTTP 400/403 — нет прав или чата
            print(f"  ✗ «{r['title']}»: {e}")
            failed += 1
            continue
        link = (resp.get("result") or {}).get("invite_link")
        if not resp.get("ok") or not link:
            print(f"  ✗ «{r['title']}»: {resp.get('description', resp)}")
            failed += 1
            continue
        set_group_invite_link(r["id"], link)
        print(f"  ✓ «{r['title']}»: {link}")
        done += 1
    print(f"записано {done}, не удалось {failed}")
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
