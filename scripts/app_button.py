"""Кнопка приложения в чате конкретного человека с @YassirAppBot (01.10.2026).

Сама кнопка ставится ботом только тем, чей канал - YassirApp
(core/app_bot.set_app_button). Этот скрипт - для проверки и поддержки:
поставить её себе, чтобы проверить вход из YassirApp на живом телефоне, или
убрать, если человеку она ни к чему.

    python scripts/app_button.py 123456789          # поставить
    python scripts/app_button.py 123456789 --remove # вернуть обычное меню

Запускать на сервере из корня репозитория: токен и адрес берутся из .env.
"""
import argparse
import json
import pathlib
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent


def env(name):
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip().strip('"')
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("uid", type=int)
    ap.add_argument("--remove", action="store_true")
    a = ap.parse_args()
    token = env("TELEGRAM_TOKEN_APP")
    if not token:
        raise SystemExit("в .env нет TELEGRAM_TOKEN_APP")
    url = (env("MUSHAF_URL") or "https://yassirilm.com/") + "?bot=app"
    button = {"type": "default"} if a.remove else \
        {"type": "web_app", "text": "YassirApp", "web_app": {"url": url}}
    req = urllib.request.Request(
        "https://api.telegram.org/bot" + token + "/setChatMenuButton",
        data=json.dumps({"chat_id": a.uid, "menu_button": button}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        print(json.loads(r.read()))


if __name__ == "__main__":
    main()
