"""Чем кончилось каждое «Отправить» в записи (23.09.2026).

Аудит после случая Азили (группа Мохидиль): 60 нажатий «Отправить», и ни
одно не дошло до сервера - телефон сам не пускал запись. По следу из
приложения (app_trail) каждое нажатие - это событие rec «send Ns file Ms Bb»,
за ним сервер отвечает submit/rev_submit. Нет ответа - запрос не ушёл.

Итог по студенту: сколько нажатий, сколько дошло, чем кончились остальные, и
СДАЛ ли он в итоге (последнее нажатие дошло или нет). «Не сдал» - главное.

    python scripts/rec_outcomes.py                       # оба бота, с 21.09
    python scripts/rec_outcomes.py --since 2026-09-22 --profile female
    python scripts/rec_outcomes.py --all                 # и благополучных тоже

Только читает. Запускать на сервере из корня репозитория.
"""
import argparse
import pathlib
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOCAL_TZ = timezone(timedelta(hours=6))
ANSWER_SEC = 120          # ответ сервера на отправку приходит за столько
SEND_RE = re.compile(r"send (\d+)s file (\?|\d+s) (\d+)b(?: from (\d+)s)?")


def ts(s):
    t = datetime.fromisoformat(s)
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def local(t):
    return t.astimezone(LOCAL_TZ).strftime("%d.%m %H:%M")


def client_block(ms, file_s, base):
    """Почему телефон мог сам не отправить - теми же правилами, что в
    index.html (hifzRecSend). Точный шаг не пишется в след, это догадка."""
    if ms < 2:
        return "короче 2 с"
    if file_s is not None:
        exp = ms - (base or 0)
        if exp - file_s >= 5 and file_s < 0.8 * exp:
            return "«не целиком» (%s из %s с)" % (file_s, exp)
    return "не ушло (сеть / этап короче минимума)"


def names(profile):
    db = ROOT / ("quran_%s.db" % profile)
    try:
        conn = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
        return {str(r[0]): r[1] for r in conn.execute("SELECT phone, name FROM users")}
    except sqlite3.Error:
        return {}


def arrived(profile):
    """Что реально дошло до группы: {telegram id: [(время, секунд)]}. След
    уходит на сервер раз в 20 с вместе с heartbeat - закрыли приложение сразу
    после отправки, и ответа в следе нет, хотя сдача дошла. Правда - в базе."""
    db = ROOT / ("quran_%s.db" % profile)
    out = defaultdict(list)
    try:
        conn = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
        for table in ("voice_submissions", "revision_recordings"):
            for phone, sent_at, dur in conn.execute(
                    "SELECT u.phone, t.sent_at, t.duration FROM %s t "
                    "JOIN users u ON u.id=t.student_id WHERE t.sent_at IS NOT NULL" % table):
                try:
                    out[str(phone)].append((ts(sent_at), dur))
                except ValueError:
                    pass
    except sqlite3.Error:
        pass
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-09-21T03:10")   # выкладка 7b8e5bd (UTC)
    ap.add_argument("--profile", choices=["male", "female"])
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    since = ts(a.since if "T" in a.since else a.since + "T00:00")

    conn = sqlite3.connect("file:%s?mode=ro" % (ROOT / "sources" / "hadiths.db"), uri=True)
    q = ("SELECT ts, user_id, profile, event, note FROM app_trail "
         "WHERE event IN ('rec','submit','rev_submit') ")
    args = []
    if a.profile:
        q += "AND profile=? "
        args.append(a.profile)
    rows = [r for r in conn.execute(q + "ORDER BY id", args) if ts(r[0]) >= since]

    by_user = defaultdict(list)
    for r in rows:
        by_user[(r[2], r[1])].append(r)

    who = {p: names(p) for p in ("male", "female")}
    got = {p: arrived(p) for p in ("male", "female")}
    total = defaultdict(int)
    for (profile, uid), evs in sorted(by_user.items()):
        sends = []
        send_times = [ts(e[0]) for e in evs if e[3] == "rec" and (e[4] or "").startswith("send")]
        for i, (t, _, _, ev, note) in enumerate(evs):
            if ev != "rec" or not (note or "").startswith("send"):
                continue
            m = SEND_RE.match(note)
            if not m:
                continue
            ms, fs, size, base = m.groups()
            file_s = None if fs == "?" else int(fs[:-1])
            t0 = ts(t)
            answer = None
            for t2, _, _, ev2, note2 in evs[i + 1:]:
                if ts(t2) - t0 > timedelta(seconds=ANSWER_SEC):
                    break
                if ev2 in ("submit", "rev_submit"):
                    answer = note2
                    break
                if ev2 == "rec" and (note2 or "").startswith("send"):
                    break
            # Сдачу из базы относим к последнему нажатию перед ней, не ко всем.
            later = [x for x in send_times if x > t0]
            until = min([t0 + timedelta(minutes=10)] + later[:1])
            if answer is None and any(
                    t0 <= at <= until for at, _ in got[profile].get(str(uid), [])):
                answer = "ok"          # в следе ответа нет, а в базе сдача есть
            if answer is None:
                outcome = client_block(int(ms), file_s, int(base) if base else 0)
            elif answer == "ok":
                outcome = "ok"
            else:
                outcome = "сервер: " + answer
            sends.append((t0, int(ms), file_s, int(size), outcome))
        if not sends:
            continue
        ok = sum(1 for s in sends if s[4] == "ok")
        bad = [s for s in sends if s[4] != "ok"]
        total["students"] += 1
        total["sends"] += len(sends)
        total["ok"] += ok
        final_ok = sends[-1][4] == "ok"
        if not final_ok:
            total["stuck"] += 1
        if bad:
            total["with_trouble"] += 1
        if not bad and not a.all:
            continue
        name = who[profile].get(str(uid), "?")
        mark = "✓ сдал" if final_ok else "✗ НЕ СДАЛ"
        print("%s %s (%s) %s: нажатий %d, дошло %d" % (profile[0].upper(), name, uid, mark, len(sends), ok))
        reasons = defaultdict(list)
        for s in bad:
            reasons[s[4]].append(s)
        for why, ss in reasons.items():
            s = ss[0]
            print("    %2d × %-45s  первое %s, таймер %ss, файл %s, %d байт"
                  % (len(ss), why, local(s[0]), s[1], "?" if s[2] is None else "%ss" % s[2], s[3]))
    print("\nстудентов с отправкой: %(students)d, нажатий: %(sends)d, дошло: %(ok)d, "
          "с проблемами: %(with_trouble)d, последнее нажатие не дошло: %(stuck)d" % total)


if __name__ == "__main__":
    main()
