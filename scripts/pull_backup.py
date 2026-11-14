# -*- coding: utf-8 -*-
"""Копия баз с сервера на компьютер Абдусаттара (14.11.2026, wiki/architecture.md, Д1).

Решение пользователя 14.11: копию вне сервера держим на его компьютере, снимаем 2-3 раза
в неделю днём, когда компьютер включён, - Claude спрашивает в начале сессии, если последней
копии больше двух дней. Скрипт: снимает свежую копию на сервере (scripts/backup_db.py),
скачивает её в папку ВНЕ репозитория (репо публичный, в базах личные данные),
проверяет, что каждая база открывается, и хранит KEEP последних копий (3 копии раз в 3 дня = охват около 9 дней; решение 14.11).

    python scripts/pull_backup.py            # снять и скачать
    python scripts/pull_backup.py --age      # только сказать, сколько дней последней копии
"""
import gzip
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing
from datetime import date
from pathlib import Path

DEST = Path.home() / "YassirBackups"
KEEP = 3
HOST = "claude-access@34.51.213.67"
SSH = ["-o", "ConnectTimeout=25", "-i", str(Path.home() / ".ssh" / "claude_gcp")]
REMOTE = "/home/stursunkul/backups/db"
NAMES = ["quran_male.db.gz", "quran_female.db.gz", "hadiths.db.gz"]


def last_age():
    days = sorted(p.name for p in DEST.glob("20??-??-??") if p.is_dir()) if DEST.exists() else []
    return (date.today() - date.fromisoformat(days[-1])).days if days else None


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if "--age" in sys.argv:
        age = last_age()
        print("копий на компьютере нет" if age is None else "последней копии дней: %d" % age)
        return
    run = "cd /home/stursunkul/yassir-bot && sudo -u stursunkul venv/bin/python3 scripts/backup_db.py"
    r = subprocess.run(["ssh", *SSH, HOST, run], capture_output=True, text=True, encoding="utf-8")
    print(r.stdout.strip())
    if r.returncode:
        sys.exit("копия на сервере не снята: " + r.stderr[-300:])
    today = date.today().isoformat()
    day = DEST / today
    day.mkdir(parents=True, exist_ok=True)
    # день на сервере считается по его часам (UTC) - берём самую свежую папку
    r = subprocess.run(["ssh", *SSH, HOST, "sudo -u stursunkul ls %s | grep ^20 | tail -1" % REMOTE],
                       capture_output=True, text=True)
    remote_day = r.stdout.strip()
    for name in NAMES:
        subprocess.run(["scp", *SSH, "%s:%s/%s/%s" % (HOST, REMOTE, remote_day, name), str(day / name)],
                       check=True, capture_output=True)
        with tempfile.TemporaryDirectory() as tmp:        # копия должна открываться
            db = Path(tmp) / "x.db"
            with gzip.open(day / name) as g, open(db, "wb") as f:
                shutil.copyfileobj(g, f)
            with closing(sqlite3.connect(str(db))) as c:
                ok = c.execute("PRAGMA integrity_check").fetchone()[0]
                tables = c.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
        if ok != "ok" or not tables:
            sys.exit("скачанная копия %s не открывается (%s)" % (name, ok))
        print("%s: %.1f МБ, таблиц %d, цела" % (name, (day / name).stat().st_size / 1e6, tables))
    days = sorted(p for p in DEST.glob("20??-??-??") if p.is_dir())
    for old in days[:-KEEP]:
        shutil.rmtree(old)
    print("копия на компьютере: %s" % day)


if __name__ == "__main__":
    main()
