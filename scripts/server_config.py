# -*- coding: utf-8 -*-
"""Настройка сервера - в git (14.11.2026, wiki/architecture.md П4).

Конфиг nginx, обе службы ботов, cron и права sudo жили только на сервере: машину нельзя
было поднять заново по записи, а правку конфига никто не видел. Теперь их копия лежит в
`server/`, а этот скрипт снимает её с сервера заново:

    python scripts/server_config.py           # скачать в server/ ; дальше `git diff server/`
    python scripts/server_config.py --check   # отличается от git - код 1 (ничего не пишет)

Секретов в этих файлах нет (ключи - в .env на сервере, в git не попадают). Скрипт только
читает сервер. Порядок правки: меняем на сервере (с «да» человека) -> запускаем скрипт ->
коммитим server/ вместе с записью в wiki/infrastructure.md.
"""
import argparse
import io
import os
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "server"
HOST = os.environ.get("YASSIR_SSH", "claude-access@34.51.213.67")
KEY = os.environ.get("YASSIR_SSH_KEY", str(Path.home() / ".ssh" / "claude_gcp"))

REMOTE = r"""
set -e
T=$(mktemp -d); mkdir -p $T/nginx $T/systemd $T/sudoers
sudo -n cat /etc/nginx/sites-available/yassir-app > $T/nginx/yassir-app
sudo -n cat /etc/nginx/nginx.conf > $T/nginx/nginx.conf
sudo -n cat /etc/systemd/system/yassir-bot.service > $T/systemd/yassir-bot.service
sudo -n cat /home/stursunkul/.config/systemd/user/yassir-bot-female.service > $T/systemd/yassir-bot-female.service
for f in yassir-bot yassir-bot-restart yassir-stop; do sudo -n cat /etc/sudoers.d/$f > $T/sudoers/$f; done
sudo -n -u stursunkul crontab -l > $T/crontab.txt
tar -C $T -cf - .
rm -rf $T
"""


def fetch():
    """{относительный путь: байты} - как сейчас на сервере."""
    raw = subprocess.run(["ssh", "-i", KEY, "-o", "ConnectTimeout=15", HOST, REMOTE],
                         check=True, capture_output=True).stdout
    files = {}
    with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
        for m in tar.getmembers():
            if m.isfile():
                files[m.name.lstrip("./")] = tar.extractfile(m).read()
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    files = fetch()
    changed = [name for name, body in sorted(files.items())
               if not (OUT / name).exists() or (OUT / name).read_bytes() != body]
    if args.check:
        if changed:
            print("сервер отличается от git: " + ", ".join(changed))
            sys.exit(1)
        print("настройка сервера совпадает с git (%d файлов)" % len(files))
        return
    for name in changed:
        (OUT / name).parent.mkdir(parents=True, exist_ok=True)
        (OUT / name).write_bytes(files[name])
    print("файлов %d, обновлено %d%s" % (len(files), len(changed),
                                         (": " + ", ".join(changed)) if changed else ""))


if __name__ == "__main__":
    main()
