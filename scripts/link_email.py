"""Привязать почту для входа в YassirApp (07.10.2026, core/email_login.py).

Для тех, кто застрял без Telegram (первый - Саламат, устаз G2C: новый айфон,
Telegram просит Premium). Почту присылает сам человек, супер-админ знает
его лично - на этом и держится, что почта действительно его.

    python scripts/link_email.py --profile male --find Саламат
    python scripts/link_email.py --profile male --user-id 123 --email a@mail.ru
    python scripts/link_email.py --profile male --user-id 123            # что привязано
    python scripts/link_email.py --remove a@mail.ru

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
    ap.add_argument("--email")
    ap.add_argument("--remove", metavar="EMAIL")
    a = ap.parse_args()

    os.environ["BOT_PROFILE"] = a.profile
    os.environ.setdefault("DB_PATH", str(ROOT / ("quran_%s.db" % a.profile)))
    sys.path.insert(0, str(ROOT))
    from core.db import db   # noqa: E402
    from core import email_login   # noqa: E402

    if a.remove:
        print("отвязана" if email_login.unlink_email(a.remove) else "такой почты нет")
        return 0

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

    if a.email:
        try:
            e = email_login.link_email(a.email, u["phone"], a.profile, added_by="link_email.py")
        except ValueError as err:
            print("не привязано: %s" % err)
            return 1
        print("привязана %s -> %s (%s, tg %s)" % (e, u["name"], a.profile, u["phone"]))
    print("%s: %s" % (u["name"], ", ".join(email_login.emails_of(u["phone"], a.profile)) or "почты нет"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
