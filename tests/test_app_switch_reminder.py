"""Утреннее «переходи в приложение» (15.09.2026): кому писать.

Письмо получает тот, кто за последние дни сдавал задания, но ни разу не
открывал приложение. Устаз-студент получает наравне со всеми (решение
пользователя), супер-админ и служебная группа - нет, без открытой лички -
писать некуда.
"""

import sqlite3
from datetime import date, datetime, timezone

import core.db as db
import core.app_trail as app_trail
import core.mushaf_words as mushaf_words
import core.scheduler as scheduler


def _seed(test_db, monkeypatch):
    db.save_group("-100", "N-1", tasks="m,r,t")
    db.save_group("-200", "Устазат", tasks="m")
    g = db.get_group("-100")
    staff = db.get_group("-200")
    with sqlite3.connect(test_db) as conn:
        conn.execute("UPDATE groups SET group_type='staff' WHERE chat_id='-200'")
    people = {}
    for name, phone in (("Текстом", "1001"), ("ВПриложении", "1002"), ("Молчит", "1003"),
                        ("БезЛички", "1004"), ("Админ", "1005"), ("УстазСтудент", "1006")):
        db.add_student(name, g["id"], phone=phone)
        people[name] = db.find_user_by_phone(phone)["id"]
    db.add_student("Служебный", staff["id"], phone="1007")
    people["Служебный"] = db.find_user_by_phone("1007")["id"]
    with sqlite3.connect(test_db) as conn:
        conn.execute("UPDATE users SET dm_ok=1 WHERE phone!='1004'")
    today = date(2026, 9, 15)
    for name in ("Текстом", "ВПриложении", "БезЛички", "Админ", "УстазСтудент", "Служебный"):
        db.save_report(people[name], g["id"] if name != "Служебный" else staff["id"],
                       "2026-09-14", {"m": True})
    db.add_group_admin(staff["id"], "1006")  # устаз другой группы, в N-1 учится как студент
    monkeypatch.setattr(scheduler, "SUPER_ADMIN_IDS", ["1005"])
    return today


def test_кому_писать(test_db, monkeypatch):
    today = _seed(test_db, monkeypatch)

    got = scheduler.app_switch_recipients(today=today, seen={"1002"})

    assert set(got) == {"1001", "1006"}
    assert got["1001"] == ("Текстом", "ru")


def test_след_в_приложении_берётся_из_app_trail(test_hadiths_db, monkeypatch):
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(mushaf_words.HADITHS_DB) as conn:
        conn.execute(app_trail._SCHEMA)
        conn.executemany(
            "INSERT INTO app_trail (ts, user_id, profile, event) VALUES (?,?,?,?)",
            [(now, "1002", "male", "open"), (now, "2002", "female", "open"),
             ("2026-01-01T00:00:00+00:00", "1009", "male", "open")])

    assert app_trail.users_seen_since("male", hours=72) == {"1002"}


def test_текст_подставляет_имя():
    from core.i18n import T
    text = T("app_switch_reminder", "ky", who=", Хамза")
    assert text.startswith("Ассаляму алейкум, Хамза!")
    assert "YassirApp" in text and "Знания" in text
    assert T("app_switch_reminder", "ru", who="").startswith("Ассаляму алейкум! ")
