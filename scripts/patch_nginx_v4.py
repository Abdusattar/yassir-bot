#!/usr/bin/env python3
"""nginx: бессрочный кэш для своих шрифтов мусхафа /v4/ (12.11.2026).

Шрифты листов (604 файла p{N}.woff2, scripts/mirror_v4_fonts.py) лежат в
/var/www/yassir-app/v4/ и не меняются никогда - телефон должен скачать каждый
один раз. Без этого правила nginx отдаёт их без Cache-Control, и браузер
решает сам, сколько держать.

Запускать на сервере от root, идемпотентно, бэкап рядом:

    sudo python3 ~/yassir-bot/scripts/patch_nginx_v4.py
    sudo nginx -t && sudo systemctl reload nginx
"""
import shutil
import sys
import time

CONF = "/etc/nginx/sites-available/yassir-app"
ANCHOR = "    location / {\n        try_files $uri $uri/ =404;"
BLOCK = """    # Шрифты листов мусхафа (QPC V4): файлы неизменны - кэш на год, без перепроверки.
    location ^~ /v4/ {
        add_header Cache-Control "public, max-age=31536000, immutable";
        add_header Access-Control-Allow-Origin *;
        try_files $uri =404;
    }

"""


def main():
    try:
        text = open(CONF, encoding="utf-8").read()
    except PermissionError:
        sys.exit("Нужен root: sudo python3 " + __file__)
    if "location ^~ /v4/" in text:
        print("Менять нечего: правило /v4/ уже стоит")
        return
    if text.count(ANCHOR) != 1:
        sys.exit("Не нашёл 'location / {' ровно один раз - конфиг изменился, правь руками")
    backup = CONF + ".bak-" + time.strftime("%Y%m%d_%H%M")
    shutil.copy(CONF, backup)
    open(CONF, "w", encoding="utf-8").write(text.replace(ANCHOR, BLOCK + ANCHOR))
    print("Бэкап:", backup)
    print("Добавлено правило /v4/. Дальше: sudo nginx -t && sudo systemctl reload nginx")


if __name__ == "__main__":
    main()
