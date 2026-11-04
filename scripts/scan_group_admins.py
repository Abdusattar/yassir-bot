"""Скан админов во всех группах бота (04.11.2026, после взлома аккаунтов сестёр).

Только читает, ничего не меняет. Для каждой группы из таблицы groups:
- права самого бота (может ли он удалять сообщения, банить, назначать админов);
- общие права участников (getChat → permissions: могут ли писать);
- список админов с правами. Помечает:
  ⚠️ ЧУЖОЙ  - админ, которого нет ни в SUPER_ADMIN_IDS, ни среди устазов
              этой группы (user_groups.role='admin');
  💀 УДАЛЁН - аккаунт удалён (имя пустое / «Deleted Account»).

    sudo -u stursunkul venv/bin/python3 scripts/scan_group_admins.py --profile female

Запускать на сервере из корня репозитория.
"""
import argparse
import json
import pathlib
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent

RIGHTS = [
    ("can_delete_messages", "удалять"),
    ("can_restrict_members", "банить"),
    ("can_promote_members", "НАЗНАЧАТЬ_АДМИНОВ"),
    ("can_change_info", "менять_инфо"),
    ("can_invite_users", "приглашать"),
    ("can_pin_messages", "закреплять"),
    ("can_manage_chat", "управлять"),
]


def env_vals(root, profile):
    env = root / (".env.female" if profile == "female" else ".env")
    vals = {}
    for line in env.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"').strip("'")
    return vals


def call(tok, method, **params):
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request("https://api.telegram.org/bot%s/%s" % (tok, method), data=data)
    try:
        return json.load(urllib.request.urlopen(req, timeout=20))
    except urllib.error.HTTPError as e:
        try:
            return json.load(e)
        except Exception:
            return {"ok": False, "description": str(e)}
    except Exception as e:
        return {"ok": False, "description": str(e)}


def rights_str(m):
    if m.get("status") == "creator":
        return "ВЛАДЕЛЕЦ (все права)"
    got = [name for key, name in RIGHTS if m.get(key)]
    return ", ".join(got) or "без прав"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="male", choices=["male", "female"])
    ap.add_argument("--root", default=str(ROOT))
    a = ap.parse_args()
    root = pathlib.Path(a.root)
    vals = env_vals(root, a.profile)
    tok = vals.get("TELEGRAM_TOKEN_" + a.profile.upper()) or vals.get("TELEGRAM_TOKEN", "")
    if not tok:
        sys.exit("нет токена")
    supers = {int(x) for x in vals.get("SUPER_ADMIN_IDS", "").replace(" ", "").split(",") if x.strip().lstrip("-").isdigit()}
    db = root / ("quran_female.db" if a.profile == "female" else "quran_male.db")
    con = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
    con.row_factory = sqlite3.Row
    groups = con.execute("SELECT id, chat_id, title, group_type FROM groups ORDER BY id").fetchall()
    me = call(tok, "getMe").get("result", {})
    bot_id = me.get("id")

    for g in groups:
        ustaz = {r["phone"] for r in con.execute(
            "SELECT u.phone FROM users u JOIN user_groups ug ON ug.user_id=u.id"
            " WHERE ug.group_id=? AND ug.role='admin'", (g["id"],))}
        ustaz = {int(p) for p in ustaz if p and str(p).lstrip("-").isdigit()}
        print("=" * 70)
        print("[%s] %s  (%s, chat %s)" % (g["id"], g["title"], g["group_type"], g["chat_id"]))
        chat = call(tok, "getChat", chat_id=g["chat_id"])
        if not chat.get("ok"):
            print("   getChat: %s" % chat.get("description"))
            continue
        perms = chat["result"].get("permissions", {})
        print("   участники могут писать: %s" % ("ДА" if perms.get("can_send_messages") else "нет"))
        adm = call(tok, "getChatAdministrators", chat_id=g["chat_id"])
        if not adm.get("ok"):
            print("   getChatAdministrators: %s" % adm.get("description"))
            continue
        for m in adm["result"]:
            u = m["user"]
            name = (u.get("first_name", "") + " " + u.get("last_name", "")).strip()
            flags = []
            if u["id"] == bot_id:
                flags.append("🤖 ЭТОТ БОТ")
            elif u.get("is_bot"):
                flags.append("🤖 бот")
            elif u["id"] in supers:
                flags.append("супер-админ")
            elif u["id"] in ustaz:
                flags.append("устаз группы")
            elif m.get("status") == "creator":
                flags.append("владелец")
            else:
                flags.append("⚠️ ЧУЖОЙ")
            if not name or name == "Deleted Account":
                flags.append("💀 УДАЛЁН")
            title = (" «%s»" % m["custom_title"]) if m.get("custom_title") else ""
            print("   %-12s %-28s @%-18s %s | %s%s" % (
                u["id"], name[:28], u.get("username", "-")[:18], " ".join(flags), rights_str(m), title))
        time.sleep(0.3)


if __name__ == "__main__":
    main()
