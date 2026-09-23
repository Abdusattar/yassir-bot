"""Ссылка на подготовительную - с заявкой (23.09.2026).

В подготовительную входят только через бота (решение пользователя): по
ссылке с заявкой Telegram не впускает сразу, а спрашивает бота, и тот
решает за секунду (core/side.py: handle_join_request). Этот скрипт выпускает
такую ссылку от имени бота и кладёт её в базу - дальше её раздаёт бот, как
раньше раздавал старую.

    python scripts/prep_request_link.py --profile male              # проверка: права, ссылка
    python scripts/prep_request_link.py --profile male --make       # выпустить и записать
    python scripts/prep_request_link.py --profile male --revoke URL # отозвать старую
    python scripts/prep_request_link.py --profile male --close-invites  # участникам нельзя приглашать

Старую ссылку не трогает, пока не попросят --revoke: сначала убеждаемся, что
первый новичок прошёл по новой. Запускать на сервере из корня репозитория
от владельца базы (stursunkul).
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


def load_env(profile):
    path = ROOT / (".env" if profile == "male" else ".env.female")
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$", line)
            if m and m.group(1) not in os.environ:
                os.environ[m.group(1)] = m.group(2).strip("\"'")


def tg(token, method, **params):
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request("https://api.telegram.org/bot%s/%s" % (token, method), data=data)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return json.load(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="male", choices=["male", "female"])
    ap.add_argument("--make", action="store_true", help="выпустить ссылку с заявкой и записать в базу")
    ap.add_argument("--revoke", metavar="URL", help="отозвать старую ссылку")
    ap.add_argument("--close-invites", action="store_true",
                    help="запретить обычным участникам приглашать (23.09.2026: основная ссылка"
                         " группы и «добавить друга» вели мимо бота)")
    a = ap.parse_args()

    os.environ["BOT_PROFILE"] = a.profile
    load_env(a.profile)
    sys.path.insert(0, str(ROOT))
    import config                                                  # noqa: E402
    from core.db import get_groups_by_type, set_group_invite_link  # noqa: E402
    token = config.TELEGRAM_TOKEN
    me = tg(token, "getMe")["result"]

    for g in get_groups_by_type("prep"):
        chat = g["chat_id"]
        print("== «%s» chat_id=%s" % (g["title"], chat))
        m = tg(token, "getChatMember", chat_id=chat, user_id=me["id"])
        r = m.get("result") or {}
        print("   бот @%s: %s, впускать/ссылки: %s" % (me["username"], r.get("status") or m.get("description"),
                                                    r.get("can_invite_users")))
        print("   ссылка в базе: %s" % (g["invite_link"] or "—"))
        perms = (tg(token, "getChat", chat_id=chat).get("result") or {}).get("permissions") or {}
        print("   участники могут приглашать: %s" % perms.get("can_invite_users"))
        if a.close_invites and perms.get("can_invite_users"):
            # Отправляем все права как были, меняем одно - иначе Telegram
            # сбросит неуказанные в «запрещено».
            perms["can_invite_users"] = False
            resp = tg(token, "setChatPermissions", chat_id=chat, permissions=json.dumps(perms),
                      use_independent_chat_permissions="true")
            print("   закрыто:", "готово" if resp.get("ok") else resp.get("description"))
        if a.revoke:
            resp = tg(token, "revokeChatInviteLink", chat_id=chat, invite_link=a.revoke)
            print("   отзыв:", "готово" if resp.get("ok") else resp.get("description"))
        if a.make:
            if not r.get("can_invite_users"):
                print("   НЕ выпускаю: у бота нет права приглашать")
                continue
            resp = tg(token, "createChatInviteLink", chat_id=chat, name="через бота",
                      creates_join_request="true")
            if not resp.get("ok"):
                print("   ошибка:", resp.get("description"))
                continue
            link = resp["result"]["invite_link"]
            set_group_invite_link(g["id"], link)
            print("   новая ссылка с заявкой записана: %s (старая жива: %s)" % (link, g["invite_link"] or "—"))


if __name__ == "__main__":
    main()
