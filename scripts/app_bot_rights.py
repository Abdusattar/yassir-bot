"""Где @YassirAppBot уже админ и каких прав не хватает (01.10.2026).

Этап 2 перехода на один бот (wiki/one_bot.md): YassirApp добавляют админом
во все группы обеих половин руками - бот сам себя не добавит. Скрипт
проходит по активным группам обеих баз и спрашивает Telegram (getChatMember
токеном YassirApp), кто он там. Только чтение: ничего не меняет.

    python scripts/app_bot_rights.py

Запускать на сервере из корня репозитория: токен берётся из .env.
"""
import json
import pathlib
import sqlite3
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
HALVES = {"male": ROOT / "quran_male.db", "female": ROOT / "quran_female.db"}

# Права, без которых YassirApp не сможет вести группу: удалять чужое,
# кикать за пропуски, выпускать ссылки и принимать заявки, закреплять.
NEEDED = {
    "can_delete_messages": "удалять сообщения",
    "can_restrict_members": "банить",
    "can_invite_users": "приглашать по ссылке",
    "can_pin_messages": "закреплять",
}


def env(name):
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip().strip('"')
    return ""


def api(token, method, **params):
    url = "https://api.telegram.org/bot" + token + "/" + method + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}")


def main():
    token = env("TELEGRAM_TOKEN_APP")
    if not token:
        raise SystemExit("в .env нет TELEGRAM_TOKEN_APP")
    me = api(token, "getMe")["result"]
    print(f"Бот: {me['first_name']} @{me['username']}\n")
    ready = total = 0
    for half, path in HALVES.items():
        c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        groups = c.execute("SELECT title, chat_id, group_type FROM groups WHERE active=1"
                           " ORDER BY group_type, title").fetchall()
        print(f"── {half}: {len(groups)}")
        for title, chat_id, gtype in groups:
            total += 1
            r = api(token, "getChatMember", chat_id=chat_id, user_id=me["id"])
            m = r.get("result") or {}
            status = m.get("status")
            if not r.get("ok"):
                line = "❌ не в группе"
            elif status in ("left", "kicked"):
                line = "❌ не в группе"
            elif status != "administrator":
                line = "⚠️ участник, не админ"
            else:
                missing = [v for k, v in NEEDED.items() if not m.get(k)]
                if missing:
                    line = "⚠️ админ, нет прав: " + ", ".join(missing)
                else:
                    line = "✅ готов"
                    ready += 1
            print(f"   {line:45} {title} [{gtype}]")
            time.sleep(0.1)
    print(f"\nГотово {ready} из {total}")


if __name__ == "__main__":
    main()
