"""Лента действий студента за последние часы - одной колонкой (13.09.2026).

Зачем: разбирать случай «у меня место сбилось» / «шрифт вылез», зайдя один
раз и ничего не спрашивая. Склеивает четыре источника по времени:
  - след из приложения (app_trail в sources/hadiths.db: тапы, выбор единицы,
    ✕, попытки сохранить место, устройство);
  - сдачи и вердикты (voice_submissions в базе бота);
  - текущее место (mushaf_hifz_pointer);
  - отчёты о шрифте fitlog из журнала мужского бота (journalctl; --no-journal
    чтобы без него).

    python scripts/user_trail.py Муслим
    python scripts/user_trail.py 201254736 --hours 24 --profile female

Запускать на сервере из корня репозитория (базы лежат там же).
"""
import argparse
import pathlib
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOCAL_TZ = timezone(timedelta(hours=6))   # Asia/Bishkek

WHAT = {"open": "открыл приложение", "page": "лист", "enter": "📖 заучивание",
        "exit": "✕ выход", "fix": "«поправить»", "unit": "единица",
        "pick": "тап выбора", "save": "сохранить место", "retake": "пересдача",
        "submit": "отправил сдачу"}


def local(ts):
    try:
        t = datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return str(ts)[:19]
    if t.tzinfo is None:
        t = t.replace(tzinfo=LOCAL_TZ)   # sent_at/verdict_at уже в +06
    return t.astimezone(LOCAL_TZ).strftime("%d.%m %H:%M:%S")


def find_users(who, profile):
    db = ROOT / ("quran_%s.db" % profile)
    conn = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT u.id, u.name, u.phone, GROUP_CONCAT(g.title, ', ') AS groups "
        "FROM users u LEFT JOIN user_groups ug ON ug.user_id=u.id "
        "LEFT JOIN groups g ON g.id=ug.group_id "
        "WHERE u.phone=? OR u.name LIKE ? GROUP BY u.id", (who, "%" + who + "%")).fetchall()
    return conn, rows


def place(page, line, stage):
    if page is None:
        return ""
    if stage == 3:
        return "стр. %s, лист" % page
    if stage == 2:
        return "стр. %s, половина от строки %s" % (page, (line or 0) + 1)
    return "стр. %s, строка %s" % (page, (line or 0) + 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("who", help="имя (часть) или Telegram ID")
    ap.add_argument("--hours", type=int, default=72)
    ap.add_argument("--profile", default="male", choices=["male", "female"])
    ap.add_argument("--no-journal", action="store_true")
    args = ap.parse_args()

    conn, users = find_users(args.who, args.profile)
    if not users:
        sys.exit("не нашёл: " + args.who)
    if len(users) > 1 and not args.who.isdigit():
        for u in users:
            print("%s  %s  [%s]" % (u["phone"], u["name"], u["groups"]))
        sys.exit("несколько - уточни по ID")
    u = users[0]
    print("== %s (%s) · %s · последние %d ч\n" % (u["name"], u["phone"], u["groups"], args.hours))
    since = datetime.now(timezone.utc) - timedelta(hours=args.hours)
    events = []

    hconn = sqlite3.connect("file:%s?mode=ro" % (ROOT / "sources" / "hadiths.db"), uri=True)
    try:
        for ts, ev, page, line, stage, note in hconn.execute(
                "SELECT ts, event, page, line, stage, note FROM app_trail "
                "WHERE user_id=? AND ts>=? ORDER BY ts, id", (u["phone"], since.isoformat())):
            events.append((ts, "след", WHAT.get(ev, ev), place(page, line, stage), note or ""))
    except sqlite3.OperationalError:
        pass
    ptr = hconn.execute("SELECT page_number, line_index, stage, updated_at FROM mushaf_hifz_pointer "
                        "WHERE user_id=?", (u["phone"],)).fetchone()

    since_local = since.astimezone(LOCAL_TZ).isoformat()
    for sent, page, line, stage, verdict, vat, rat in conn.execute(
            "SELECT sent_at, hifz_page, hifz_line, hifz_stage, verdict, verdict_at, reviewed_at "
            "FROM voice_submissions WHERE student_id=? AND (sent_at>=? OR verdict_at>=?)",
            (u["id"], since_local, since_local)):
        src = "из приложения" if page is not None else "голосом в группу"
        events.append((sent, "сдача", src, place(page, line, stage), ""))
        if vat:
            events.append((vat, "устаз", "вердикт " + str(verdict), place(page, line, stage), ""))
        elif rat:
            events.append((rat, "устаз", "разобрал", place(page, line, stage), ""))

    if not args.no_journal:
        try:
            out = subprocess.run(
                ["journalctl", "-u", "yassir-bot", "--since", "%d hours ago" % args.hours,
                 "--no-pager", "-o", "short-iso"], capture_output=True, text=True, timeout=60).stdout
            for m in re.finditer(r"^(\S+) .*fitlog user=%s (.*?) (?:iOS|Android|other)" % u["phone"],
                                 out, re.M):
                events.append((m.group(1), "шрифт", m.group(2)[:110], "", ""))
        except (OSError, subprocess.SubprocessError):
            pass

    for ts, kind, what, where, note in sorted(events, key=lambda e: local(e[0])):
        print("%s  %-6s %-22s %-32s %s" % (local(ts), kind, what, where, note))
    if ptr:
        print("\nместо сейчас: %s (обновлено %s)" % (place(ptr[0], ptr[1], ptr[2]), local(ptr[3])))
    else:
        print("\nместа нет (в заучивание не заходил)")


if __name__ == "__main__":
    main()
