# -*- coding: utf-8 -*-
"""Синхронизация команды - автоматом, из хуков Claude Code (12.11.2026).

Решение пользователя: «мы люди забывчивые» - то, что раньше было правилом в CLAUDE.md
(обновиться, прочитать логи напарника, отправить свой лог, не лезть в те же файлы),
делает код. Хуки в .claude/settings.json (он в git - действует у всех, кто работает в
репо через Claude Code):

    SessionStart      -> python scripts/team_sync.py start
    UserPromptSubmit  -> python scripts/team_sync.py prompt

Что делает сам:
  1. git fetch (на старте всегда, дальше не чаще раза в 10 минут).
  2. На старте подтягивает чужие коммиты, если это можно сделать без слияния
     (fast-forward) и они не задевают твои незакоммиченные файлы.
  3. Отправляет сегодняшний лог (logs/terminal/<сегодня>*.md): коммит только этого файла
     и пуш. Такой пуш не гоняет тесты и не перезапускает ботов (pre-push хук, deploy.yml).

Чего НЕ делает никогда: не коммитит и не пушит код. Пуш в master - это выкатка на прод,
её делает человек с Claude осознанно, законченным куском. Лог тоже не уйдёт, если вместе
с ним в master улетели бы твои незапушенные коммиты с кодом.

О чём предупреждает (текст уходит Claude в контекст, он скажет человеку):
  - напарник запушил правки в файлы, которые у тебя изменены и не отправлены, - конфликт
    лучше узнать сейчас, а не через полдня;
  - что нового у напарника: заголовки разделов его логов (в т.ч. строки «в работе»);
  - у тебя давно лежат незапушенные коммиты или несохранённые правки кода.

Скрипт никогда не мешает работе: любая ошибка или таймаут - молча выходит с кодом 0.
Выключить у себя: переменная окружения YASSIR_TEAM_SYNC=off.
"""
import datetime
import json
import os
import pathlib
import re
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATE = ROOT / ".git" / "team_sync.json"
FETCH_EVERY = 600          # с
LOG_PUSH_EVERY = 600       # с
NAG_EVERY = 3600           # с: напоминание о несохранённом коде
STALE_AFTER = 2 * 3600     # с: правка кода старше - напомнить
DOCS = re.compile(r"^(logs/|wiki/|context/|CLAUDE\.md$)")
CODE = re.compile(r"^(app_src/|core/|handlers/|tests/|scripts/|\.github/|\.githooks/|[^/]+\.py$)")
BUILT = "mushaf_data/index.html"   # результат сборки: пересекается всегда, решается пересборкой


def git(*args, timeout=20):
    r = subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=ROOT, capture_output=True,
                       timeout=timeout, encoding="utf-8", errors="replace")
    # слева не обрезать: в `git status --porcelain` первый столбец - пробел
    return r.returncode, (r.stdout or "").rstrip(), (r.stderr or "").strip()


def lines(*args):
    code, out, _ = git(*args)
    return [x for x in out.splitlines() if x.strip()] if code == 0 else []


def load():
    try:
        return json.loads(STATE.read_text("utf-8"))
    except Exception:
        return {}


def save(st):
    try:
        STATE.write_text(json.dumps(st), "utf-8")
    except Exception:
        pass


def dirty_files():
    """Изменённые и новые файлы рабочей копии (пути как в git)."""
    out = []
    for ln in lines("status", "--porcelain", "--untracked-files=normal"):
        path = ln[3:].split(" -> ")[-1].strip().strip('"')
        out.append(path)
    return out


def push_log(st, say):
    """Сегодняшний лог - коммит одного файла и пуш, если это безопасно."""
    today = datetime.date.today().isoformat()
    mine = [f for f in dirty_files() if f.startswith("logs/terminal/" + today) and f.endswith(".md")]
    if not mine or time.time() - st.get("log_push", 0) < LOG_PUSH_EVERY:
        return
    if lines("rev-parse", "--abbrev-ref", "HEAD") != ["master"]:
        return
    if lines("rev-list", "--count", "HEAD..origin/master") != ["0"]:
        say("Лог не отправлен: на GitHub есть новые коммиты - сначала git pull.")
        return
    ahead = lines("diff", "--name-only", "origin/master..HEAD")
    if any(not DOCS.match(f) for f in ahead):
        return          # вместе с логом ушёл бы незапушенный код - это решает человек
    st["log_push"] = time.time()
    git("add", "--", *mine)
    code, _, err = git("commit", "-q", "-m", "docs(logs): лог %s (авто)" % today, "--", *mine)
    if code:
        return
    code, _, err = git("push", "-q", "origin", "master", timeout=40)
    if code:
        say("Лог закоммичен, но пуш не прошёл (%s) - отправь вручную." % (err.splitlines()[-1][:120] if err else "ошибка"))


def main():
    if os.environ.get("YASSIR_TEAM_SYNC", "").lower() == "off":
        return
    mode = sys.argv[1] if len(sys.argv) > 1 else "prompt"
    st, out = load(), []
    say = out.append
    now = time.time()

    if mode == "start" or now - st.get("fetch", 0) > FETCH_EVERY:
        if git("fetch", "-q", "origin", timeout=25)[0] == 0:
            st["fetch"] = now

    behind = lines("rev-list", "--count", "HEAD..origin/master")
    behind = int(behind[0]) if behind else 0
    incoming = lines("diff", "--name-only", "HEAD...origin/master") if behind else []
    dirty = dirty_files()
    unpushed_files = lines("diff", "--name-only", "origin/master...HEAD")
    mine = set(dirty) | set(unpushed_files)
    overlap = sorted((set(incoming) & mine) - {BUILT})

    if behind:
        key = lines("rev-parse", "origin/master")[0]
        fresh = st.get("seen") != key
        # Заголовки разделов из логов напарника - до подтягивания, пока диапазон не пуст.
        heads = [ln[4:].strip() for ln in lines("diff", "--unified=0", "HEAD...origin/master", "--", "logs/terminal")
                 if ln.startswith("+## ")]
        if overlap:
            say("ПЕРЕСЕЧЕНИЕ: напарник запушил правки в файлы, которые изменены у тебя и не отправлены: "
                + ", ".join(overlap[:8]) + ". Скажи об этом человеку сейчас; перед продолжением - "
                "git pull и разбор, пока расхождение маленькое.")
        elif BUILT in incoming and BUILT in mine:
            say("Напарник обновил приложение (app_src), у тебя тоже есть правки в нём, но в других "
                "кусках: git pull, конфликт в mushaf_data/index.html решается пересборкой "
                "(python scripts/build_app.py).")
        if mode == "start" and not overlap:
            code, _, _ = git("merge", "-q", "--ff-only", "origin/master", timeout=30)
            if code == 0:
                say("Подтянул с GitHub %d новых коммитов (без слияния)." % behind)
                behind = 0
        if behind and fresh and not overlap:
            say("На GitHub %d новых коммитов - сделай git pull, когда будет удобно." % behind)
        if fresh:
            if heads:
                say("Новое в логах напарника: " + " | ".join(h[:110] for h in heads[-6:]))
            st["seen"] = key

    # Свои незапушенные коммиты и несохранённый код - напоминание не чаще раза в час.
    if mode == "start" or now - st.get("nag", 0) > NAG_EVERY:
        notes = []
        ahead = lines("log", "--format=%ct", "origin/master..HEAD")
        if ahead:
            age = (now - min(int(x) for x in ahead)) / 3600
            if mode == "start" or age > 2:
                notes.append("%d незапушенных коммитов, старшему %.0f ч" % (len(ahead), age))
        old = []
        for f in dirty:
            if CODE.match(f) and f != BUILT:
                try:
                    if now - (ROOT / f).stat().st_mtime > STALE_AFTER:
                        old.append(f)
                except OSError:
                    pass
        if old:
            notes.append("несохранённые правки кода старше 2 ч: " + ", ".join(old[:6])
                         + (" и ещё %d" % (len(old) - 6) if len(old) > 6 else ""))
        if notes:
            st["nag"] = now
            say("Не отправлено: " + "; ".join(notes) + ". Законченное - закоммитить и запушить "
                "маленьким куском; незаконченное - одной строкой в лог, что это и чьё.")

    push_log(st, say)
    if mode == "start":
        say("Начинаешь задачу - первой строкой в сегодняшний лог: «## [Блок] в работе с ЧЧ:ММ: какие "
            "файлы» (карта блоков - wiki/README.md). Лог отправится сам.")
    save(st)
    if out:
        sys.stdout.reconfigure(encoding="utf-8")
        print("[team_sync] " + "\n[team_sync] ".join(out))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
