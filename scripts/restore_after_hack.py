"""Вернуть в группы сестёр/братьев после взлома их Telegram-аккаунтов (31.10.2026).

Зачем: 31.10 с пяти взломанных аккаунтов в Тадаббур сестёр ушла фишинговая
ссылка «Чат переносится в новую группу», после каждой отправки аккаунт сам
выходил из группы, а админ потом забанил их вручную. Такой бан бессрочный,
бот его не снимет (в подготовительной снимает сам - lift_prep_ban). Когда
аккаунты вернулись к хозяйкам, их надо пустить обратно.

Что делает для каждого человека из --uids и каждой группы из --groups,
где человек числился (user_groups) и сейчас не участник (kicked/left):
снимает бан (only_if_banned), создаёт личную ссылку на ОДИН вход на 7 дней
и шлёт в личку от бота текст из --text-file, подставив {name} и {links}.
Админов не трогает. Без --apply ничего не меняет - только показывает.

    sudo -u stursunkul venv/bin/python3 scripts/restore_after_hack.py \
        --profile female --uids 467275183,686247348 --groups 2,13 \
        --text-file /tmp/hack.txt            # показать
        ... --apply                          # сделать

Запускать на сервере из корня репозитория от владельца базы (stursunkul).
"""
import argparse
import json
import pathlib
import sqlite3
import sys
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
LINK_TTL = 7 * 24 * 3600


def token(root, profile):
    env = root / (".env.female" if profile == "female" else ".env")
    vals = {}
    for line in env.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"').strip("'")
    return vals.get("TELEGRAM_TOKEN_" + profile.upper()) or vals.get("TELEGRAM_TOKEN", "")


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="male", choices=["male", "female"])
    ap.add_argument("--uids", required=True, help="Telegram ID через запятую")
    ap.add_argument("--groups", required=True, help="groups.id через запятую")
    ap.add_argument("--text-file", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--root", default=str(ROOT), help="корень репозитория (база и .env)")
    a = ap.parse_args()
    root = pathlib.Path(a.root)

    template = pathlib.Path(a.text_file).read_text(encoding="utf-8").strip()
    c = sqlite3.connect(str(root / ("quran_%s.db" % a.profile)))
    c.row_factory = sqlite3.Row
    tok = token(root, a.profile)
    gids = [int(x) for x in a.groups.split(",") if x.strip()]
    groups = {g["id"]: g for g in c.execute(
        "SELECT id, chat_id, title FROM groups WHERE id IN (%s)" % ",".join("?" * len(gids)), gids)}

    for uid in [x.strip() for x in a.uids.split(",") if x.strip()]:
        u = c.execute("SELECT id, name, phone, dm_ok FROM users WHERE phone=?", (uid,)).fetchone()
        if not u:
            print("%s: нет в базе" % uid)
            continue
        if c.execute("SELECT 1 FROM user_groups WHERE user_id=? AND role='admin'", (u["id"],)).fetchone():
            print("%s %s: админ - не трогаю" % (uid, u["name"]))
            continue
        print("== %s (%s), личка открыта: %s" % (u["name"], uid, "да" if u["dm_ok"] else "НЕТ"))
        links = []
        for gid in gids:
            g = groups.get(gid)
            if not g:
                continue
            m = call(tok, "getChatMember", chat_id=g["chat_id"], user_id=uid)
            status = m["result"]["status"] if m.get("ok") else "? %s" % m.get("description")
            # Бан в Telegram - сам по себе знак, что человек тут был: в
            # Тадаббур бот не регистрирует, строки user_groups может не быть.
            was_here = status == "kicked" or c.execute(
                "SELECT 1 FROM user_groups WHERE user_id=? AND group_id=?", (u["id"], gid)).fetchone()
            if not was_here:
                continue
            if status not in ("kicked", "left"):
                print("   %s: %s - не нужно" % (g["title"], status))
                continue
            if not a.apply:
                print("   %s: %s - сниму бан и дам ссылку" % (g["title"], status))
                links.append("• %s: <ссылка>" % g["title"])
                continue
            if status == "kicked":
                r = call(tok, "unbanChatMember", chat_id=g["chat_id"], user_id=uid, only_if_banned="true")
                print("   %s: бан снят: %s" % (g["title"], r.get("ok")))
            r = call(tok, "createChatInviteLink", chat_id=g["chat_id"], member_limit=1,
                     expire_date=int(time.time()) + LINK_TTL, name=("возврат %s" % uid)[:32])
            if not r.get("ok"):
                print("   %s: ссылку не создал: %s" % (g["title"], r.get("description")))
                continue
            links.append("• %s: %s" % (g["title"], r["result"]["invite_link"]))
            time.sleep(0.1)
        if not links:
            print("   возвращать некуда")
            continue
        text = template.format(name=u["name"], links="\n".join(links))
        print("-" * 40)
        print(text)
        print("-" * 40)
        if not a.apply:
            continue
        if not u["dm_ok"]:
            print("   НЕ отправлено: не нажимала «Старт» - ссылки выше передать вручную")
            continue
        r = call(tok, "sendMessage", chat_id=uid, text=text, disable_web_page_preview="true")
        print("   отправлено" if r.get("ok") else "   НЕ отправлено: %s" % r.get("description"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
