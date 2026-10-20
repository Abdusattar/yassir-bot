"""Ссылка для входа в YassirApp без Telegram и без почты (20.10.2026,
core/web_auth.py: new_login_link).

Для тех, кого Telegram не пускает (просит Premium). Супер-админ знает
человека лично и сам шлёт ему ссылку (WhatsApp). Ссылка одноразовая и живёт
сутки: открыл - вошёл на этом телефоне, второй раз она уже не сработает.

    python scripts/login_link.py --profile female --find Али
    python scripts/login_link.py --profile female --user-id 2639
    python scripts/login_link.py --profile female --user-id 2639 --hours 48

Запускать на сервере из корня репозитория от владельца базы (stursunkul).
"""
import argparse
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="male", choices=["male", "female"])
    ap.add_argument("--find", help="часть имени - показать кандидатов с users.id")
    ap.add_argument("--user-id", type=int, help="users.id в базе этой половины")
    ap.add_argument("--hours", type=int, default=24)
    a = ap.parse_args()

    os.environ["BOT_PROFILE"] = a.profile
    os.environ.setdefault("DB_PATH", str(ROOT / ("quran_%s.db" % a.profile)))
    sys.path.insert(0, str(ROOT))
    import config   # noqa: E402
    from core.db import db, is_app_member   # noqa: E402
    from core import web_auth   # noqa: E402

    if a.find:
        with db() as c:
            rows = c.execute(
                "SELECT u.id, u.name, u.phone, GROUP_CONCAT(g.title || ':' || ug.role, ', ') AS gr"
                " FROM users u LEFT JOIN user_groups ug ON ug.user_id=u.id AND ug.active=1"
                " LEFT JOIN groups g ON g.id=ug.group_id"
                " WHERE u.name LIKE ? GROUP BY u.id", ("%" + a.find + "%",)).fetchall()
        for r in rows:
            print("  id=%-5s %-25s tg=%-12s %s" % (r["id"], r["name"], r["phone"], r["gr"] or "-"))
        return 0

    if not a.user_id:
        ap.error("нужен --user-id (или --find)")
    with db() as c:
        u = c.execute("SELECT id, name, phone FROM users WHERE id=?", (a.user_id,)).fetchone()
    if not u or not u["phone"]:
        print("нет пользователя %s или у него нет Telegram ID" % a.user_id)
        return 1
    # Приложение всё равно не пустит того, кто не числится в группах этой
    # половины, - ссылка ему ни к чему.
    if not is_app_member(u["phone"]):
        print("%s не числится ни в одной группе %s - приложение его не пустит" % (u["name"], a.profile))
        return 1

    code = web_auth.new_login_link(u["phone"], a.profile, hours=a.hours)
    print("%s (%s, tg %s), ссылка на %d ч, одноразовая:" % (u["name"], a.profile, u["phone"], a.hours))
    print(config.MUSHAF_URL.rstrip("/") + "/#login=" + code)
    return 0


if __name__ == "__main__":
    sys.exit(main())
