"""Кто и как идёт через личку @YassirAppBot (01.10.2026, core/app_route.py).

Зачем: в первые дни круга «новички» видеть каждого новичка одним взглядом,
ничего не спрашивая: когда пришёл к YassirApp, новичок ли, не заблокировал
ли, где сейчас (подготовительная / группа / нигде, в какой половине), его
нажатия из очереди app_inbox (взяты ли процессом половины) и строки журнала
ботов про запасной путь («через YassirApp не прошёл»).

    python scripts/app_route_status.py            # за 24 часа
    python scripts/app_route_status.py --hours 72
    python scripts/app_route_status.py --no-journal

Запускать на сервере из корня репозитория (базы лежат там же). Только чтение.
"""
import argparse
import pathlib
import sqlite3
import subprocess
from datetime import datetime, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
HADITHS = ROOT / "sources" / "hadiths.db"
HALVES = {"male": ROOT / "quran_male.db", "female": ROOT / "quran_female.db"}


def ro(path):
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    c.row_factory = sqlite3.Row
    return c


def where(uid):
    """[(половина, имя, группа, тип, активен, dm_ok своего бота)]."""
    out = []
    for half, path in HALVES.items():
        if not path.exists():
            continue
        with ro(path) as c:
            u = c.execute("SELECT id, name, dm_ok FROM users WHERE phone=?", (uid,)).fetchone()
            if not u:
                continue
            rows = c.execute(
                "SELECT g.title, g.group_type, ug.active FROM user_groups ug"
                " JOIN groups g ON g.id=ug.group_id WHERE ug.user_id=? ORDER BY ug.active DESC",
                (u["id"],)).fetchall()
            if not rows:
                out.append((half, u["name"], "—", "", 0, u["dm_ok"]))
            for r in rows:
                out.append((half, u["name"], r["title"], r["group_type"], r["active"], u["dm_ok"]))
    return out


def table_exists(c, name):
    return c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--no-journal", action="store_true")
    a = ap.parse_args()
    since = (datetime.now() - timedelta(hours=a.hours)).strftime("%Y-%m-%d %H:%M:%S")

    with ro(HADITHS) as c:
        if not table_exists(c, "app_dm"):
            print("app_dm ещё нет - YassirApp ни с кем не встречался после 01.10")
            return
        people = c.execute("SELECT * FROM app_dm WHERE started_at>=? ORDER BY started_at",
                           (since,)).fetchall()
        inbox = c.execute("SELECT * FROM app_inbox WHERE created_at>=? ORDER BY id",
                          (since,)).fetchall() if table_exists(c, "app_inbox") else []
        sides = {r["user_id"]: r["side"] for r in c.execute("SELECT user_id, side FROM user_side")} \
            if table_exists(c, "user_side") else {}

    print(f"── Пришли к YassirApp за {a.hours} ч: {len(people)}")
    for p in people:
        flag = "НОВИЧОК" if p["newcomer"] else "старый"
        blocked = f"  ⛔ заблокировал {p['blocked_at']}" if p["blocked_at"] else ""
        print(f"\n{p['user_id']}  {p['started_at']}  {flag}  ответил: {sides.get(p['user_id'], '—')}{blocked}")
        for half, name, title, gtype, active, dm_ok in where(p["user_id"]):
            print(f"   {half:6} {name or '(без имени)':20} {title} [{gtype}] "
                  f"{'активен' if active else 'не активен'}  личка своего бота: {'да' if dm_ok else 'нет'}")
        for r in inbox:
            if r["user_id"] == p["user_id"]:
                print(f"   ↳ {r['created_at']} {r['kind']} {r['data'] or ''} -> {r['profile']}"
                      f"  {'взято ' + r['taken_at'] if r['taken_at'] else '⏳ НЕ ВЗЯТО'}")

    stuck = [r for r in inbox if not r["taken_at"]]
    if stuck:
        print(f"\n⚠️ Не взято из очереди: {len(stuck)} (процесс половины не забирает?)")

    if a.no_journal:
        return
    print("\n── Журнал: запасной путь и очередь")
    cmds = [["journalctl", "-u", "yassir-bot", "--since", since, "--no-pager"],
            ["journalctl", "--user", "-u", "yassir-bot-female", "--since", since, "--no-pager"]]
    for cmd in cmds:
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout
        except Exception as e:
            print("   журнал недоступен:", e)
            continue
        for line in out.splitlines():
            if any(k in line for k in ("через YassirApp не прошёл", "недоступен через YassirApp",
                                       "app_inbox", "app_bot", "tg_call app ", "app sendPhoto")):
                print("  ", line[-220:])


if __name__ == "__main__":
    main()
