#!/usr/bin/env python3
"""Правка nginx под вход с сайта и PWA (10.09.2026).

Запускать на сервере от root:

    sudo python3 ~/yassir-bot/scripts/patch_nginx_pwa.py
    sudo nginx -t && sudo systemctl reload nginx

Делает ровно две вещи, обе идемпотентно — повторный запуск ничего не портит
и честно скажет, что менять нечего.

1. `proxy_set_header X-Real-IP $remote_addr` в обе локации /api/muf/.
   Без него настоящий адрес клиента до приложения не доходит: за nginx
   request.remote всегда 127.0.0.1, и заслон от перебора на входе считает
   всех студентов за одного. В коде это предусмотрено (порог тогда
   автоматически поднимается до общего, см. _login_rate_ok в
   core/mufradat_api.py), но различать людей всё-таки лучше.

2. `no-cache` для sw.js и manifest.json — тем же правилом, что уже стоит на
   index.html и page*.json. Они точно так же обновляются НА МЕСТЕ, а
   зависший в браузере service worker держал бы старую версию приложения
   куда упрямее, чем обычный файл (см. wiki/mushaf_yassirapp.md, случай
   29.08.2026).
"""
import shutil
import sys
import time

CONF = "/etc/nginx/sites-available/yassir-app"

HOST_HEADER = "proxy_set_header Host $host;"
REAL_IP = "proxy_set_header X-Real-IP $remote_addr;"

OLD_LOCATION = "^/(index\\.html|page"
NEW_LOCATION = "^/(index\\.html|sw\\.js|manifest\\.json|page"


def main():
    try:
        text = open(CONF, encoding="utf-8").read()
    except PermissionError:
        sys.exit("Нужен root: sudo python3 " + __file__)
    except FileNotFoundError:
        sys.exit("Не нашёл " + CONF)

    original = text
    done = []

    if REAL_IP in text:
        done.append("X-Real-IP уже стоял")
    else:
        n = text.count(HOST_HEADER)
        if not n:
            sys.exit("Не нашёл '" + HOST_HEADER + "' — конфиг изменился, "
                     "правь руками")
        text = text.replace(HOST_HEADER, HOST_HEADER + "\n        " + REAL_IP)
        done.append("X-Real-IP добавлен в %d локаций" % n)

    if NEW_LOCATION in text:
        done.append("no-cache для sw.js/manifest.json уже стоял")
    elif OLD_LOCATION in text:
        text = text.replace(OLD_LOCATION, NEW_LOCATION)
        done.append("no-cache расширен на sw.js и manifest.json")
    else:
        sys.exit("Не нашёл location с index.html|page — конфиг изменился, "
                 "правь руками")

    if text == original:
        print("Менять нечего:")
        for line in done:
            print("  •", line)
        return

    backup = CONF + ".bak-" + time.strftime("%Y%m%d_%H%M")
    shutil.copy(CONF, backup)
    open(CONF, "w", encoding="utf-8").write(text)

    print("Бэкап:", backup)
    for line in done:
        print("  •", line)
    print("\nТеперь: sudo nginx -t && sudo systemctl reload nginx")


if __name__ == "__main__":
    main()
