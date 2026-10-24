"""Снять вечные баны в подготовительной (24.10.2026).

В подготовительной пробовать можно сколько угодно раз, а ручное «Удалить
участника» устаза оставляет бан навсегда - человек видит «ссылка
недействительна». С 24.10 бот снимает такой бан сам (lift_prep_ban), а этот
скрипт - для банов, поставленных раньше. Список забаненных Bot API не даёт,
поэтому спрашиваем статус у всех, кого база знает в подготовительной:
user_groups, unregistered_members и авторы сообщений в её ленте.

    python scripts/prep_unban.py --profile female            # только показать
    python scripts/prep_unban.py --profile female --apply    # снять баны

Запускать на сервере из корня репозитория от владельца базы (stursunkul).
"""
import argparse
import json
import pathlib
import sqlite3
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent


def token(profile):
    env = ROOT / (".env.female" if profile == "female" else ".env")
    vals = {}
    for line in env.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"').strip("'")
    return vals.get("TELEGRAM_TOKEN_" + profile.upper()) or vals.get("TELEGRAM_TOKEN", "")


def call(tok, method, **params):
    url = "https://api.telegram.org/bot%s/%s?%s" % (tok, method, urllib.parse.urlencode(params))
    try:
        return json.load(urllib.request.urlopen(url, timeout=20))
    except Exception as e:
        return {"ok": False, "description": str(e)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="male", choices=["male", "female"])
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    c = sqlite3.connect(str(ROOT / ("quran_%s.db" % a.profile)))
    c.row_factory = sqlite3.Row
    tok = token(a.profile)
    groups = c.execute("SELECT id, chat_id, title FROM groups WHERE group_type='prep'").fetchall()
    for g in groups:
        uids = {r["phone"] for r in c.execute(
            "SELECT u.phone FROM user_groups ug JOIN users u ON u.id=ug.user_id"
            " WHERE ug.group_id=?", (g["id"],))}
        uids |= {r["user_id"] for r in c.execute(
            "SELECT user_id FROM unregistered_members WHERE chat_id=?", (g["chat_id"],))}
        uids |= {r["sender_id"] for r in c.execute(
            "SELECT DISTINCT sender_id FROM feed_messages WHERE chat_id=? AND is_bot=0",
            (g["chat_id"],))}
        uids = sorted(u for u in uids if u and str(u).isdigit())
        print("== %s (%s): проверяю %d человек" % (g["title"], g["chat_id"], len(uids)))
        for uid in uids:
            r = call(tok, "getChatMember", chat_id=g["chat_id"], user_id=uid)
            if not r.get("ok") or r["result"]["status"] != "kicked":
                time.sleep(0.05)
                continue
            name = r["result"]["user"].get("first_name", "")
            if a.apply:
                u = call(tok, "unbanChatMember", chat_id=g["chat_id"], user_id=uid, only_if_banned="true")
                print("  %s %s - бан снят: %s" % (uid, name, u.get("ok")))
            else:
                print("  %s %s - бан" % (uid, name))
            time.sleep(0.05)


if __name__ == "__main__":
    main()
