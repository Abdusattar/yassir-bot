# -*- coding: utf-8 -*-
"""Наблюдение за сервером (14.11.2026, wiki/architecture.md: слой 3, правило 5, долги П2/П3).

Раз в 5 минут из cron. Проверяет то, о чём иначе узнали бы от студентов:
  - отвечает ли мужской бот (порт 8081) и женский (8082) - сам процесс, а не «служба active»;
  - свободно ли место на диске (тревога от 90%);
  - снялась ли ночная копия баз (scripts/backup_db.py): папке последней копии не больше
    30 часов и в последнем запуске нет строки «ОШИБКА».
О каждой беде пишет админу в Telegram ОДИН раз, и ещё раз - когда она прошла.
Токен и получатель - из .env (TELEGRAM_TOKEN, SUPER_ADMIN_IDS или MONITOR_CHAT_ID):
в самом скрипте секретов нет (прежний monitor.sh держал токен в тексте и видел только
мужского бота).

    */5 * * * * cd /home/stursunkul/yassir-bot && venv/bin/python3 scripts/monitor.py
    python scripts/monitor.py --dry      # показать, что нашёл, никому не писать
"""
import json
import os
import shutil
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = Path.home() / ".yassir_monitor.json"
BACKUPS = Path.home() / "backups" / "db"
DISK_LIMIT = 90          # % занятого
BACKUP_MAX_AGE_H = 30    # ночная копия раз в сутки + запас


def read_env(path):
    out = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def check_port(port):
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/api/muf/version" % port, timeout=8) as r:
            return r.status == 200
    except Exception:
        return False


def disk_used_percent(path="/"):
    u = shutil.disk_usage(path)
    return round(100 * (u.total - u.free) / u.total)


def backup_problem(backups=BACKUPS, now=None, max_age_h=BACKUP_MAX_AGE_H):
    """None, если ночная копия свежая и без ошибок; иначе - что не так."""
    now = now or time.time()
    days = sorted(p for p in backups.glob("20??-??-??") if p.is_dir()) if backups.exists() else []
    if not days:
        return "копий баз нет вообще"
    last = days[-1]
    files = list(last.glob("*.gz"))
    if len(files) < 3:
        return "в последней копии (%s) баз %d из 3" % (last.name, len(files))
    age_h = (now - max(f.stat().st_mtime for f in files)) / 3600
    if age_h > max_age_h:
        return "последней копии баз %d ч (%s)" % (age_h, last.name)
    log = backups / "backup.log"
    if log.exists():
        tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-6:]
        if any("ОШИБКА" in line for line in tail):
            return "последний запуск копии закончился ошибкой"
    return None


def refresh_data_manifest(data_dir=None, now=None):
    """Список отпечатков мусхафа отстал от файлов (кто-то поправил лист или перевод и не
    пересобрал) - пересобрать самому: шаг, который можно забыть, должен запускаться сам
    (wiki/architecture.md, слой 2). Дёшево: сверяется время правки, хэши считаются
    только когда файл новее списка. Возвращает текст беды или None."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from scripts import build_data_manifest as bdm
    data_dir = Path(data_dir) if data_dir else bdm.DEFAULT_DIR
    man = data_dir / bdm.NAME
    try:
        newest = 0.0
        for folder, deep in ((data_dir, False), (data_dir / "dm", False),
                             (data_dir / "meaning", True), (data_dir / "wbw", True)):
            if not folder.is_dir():
                continue
            for f in (folder.glob("*/*.json") if deep else folder.glob("page*.json")):
                newest = max(newest, f.stat().st_mtime)
        if man.exists() and man.stat().st_mtime >= newest:
            return None
        _, changed = bdm.build(data_dir)
        if not changed:
            os.utime(str(man), None)     # содержимое то же - просто отметить, что сверено
        return None
    except Exception as e:  # noqa: BLE001 - наблюдение не должно падать само
        return "список отпечатков мусхафа не пересобрался: %s" % e


def find_problems():
    problems = {}
    m = refresh_data_manifest()
    if m:
        problems["manifest"] = m
    if not check_port(8081):
        problems["male"] = "мужской бот не отвечает (порт 8081)"
    if not check_port(8082):
        problems["female"] = "женский бот не отвечает (порт 8082)"
    used = disk_used_percent()
    if used >= DISK_LIMIT:
        problems["disk"] = "диск занят на %d%%" % used
    b = backup_problem()
    if b:
        problems["backup"] = b
    return problems


def diff(old, new):
    """Что сказать: новые беды и то, что прошло. Повторно о той же беде не пишем."""
    lines = ["⚠️ " + new[k] for k in new if k not in old]
    lines += ["✅ прошло: " + old[k] for k in old if k not in new]
    return lines


def send(text, env):
    token = env.get("TELEGRAM_TOKEN", "")
    chat = env.get("MONITOR_CHAT_ID") or (env.get("SUPER_ADMIN_IDS") or env.get("ADMIN_IDS") or "").split(",")[0].strip()
    if not token or not chat:
        return False
    data = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
    try:
        urllib.request.urlopen("https://api.telegram.org/bot%s/sendMessage" % token, data=data, timeout=15)
        return True
    except Exception:
        return False


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    new = find_problems()
    if "--dry" in sys.argv:
        print(new or "всё в порядке")
        return
    try:
        old = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        old = {}
    lines = diff(old, new)
    if lines:
        if send("Яссир, сервер:\n" + "\n".join(lines), read_env(ROOT / ".env")):
            STATE.write_text(json.dumps(new, ensure_ascii=False), encoding="utf-8")
        # не отправилось - состояние не трогаем, через 5 минут попробуем снова


if __name__ == "__main__":
    main()
