"""Три ночи - по месту студента (24.10.2026).

Случай Ханумы (Эр-Рияд, на 3 часа позади Бишкека): три ночи Бишкека - её
полночь. Сдача в 01:23 по Эр-Рияду уезжала в «завтра»: вечером приложение
говорило «всё сдано», а прошедший день оставался пропуском (19.10, 22.10).
Решение пользователя: учебный день - с трёх до трёх по поясу студента;
итоги дня/недели - когда день кончился у всех.
"""
from datetime import datetime

import pytz

import core.db as db
from tests.test_study_day import at


def _student(name, phone, tz=None):
    g = db.get_group("-100551")
    if not g:
        db.save_group("-100551", "TZ group", tasks="m,r,t")
        g = db.get_group("-100551")
    sid = db.add_student(name, g["id"], phone=phone)
    if tz:
        db.set_user_tz(phone, tz)
    return sid, g


def test_riyadh_night_counts_for_her_yesterday(test_db, monkeypatch):
    sid, _ = _student("Ханума", "800", "Asia/Riyadh")
    other, _ = _student("Бишкек", "801")
    at(monkeypatch, 4, 23, day=23, month=10)        # 04:23 Бишкек = 01:23 Эр-Рияд
    assert db.get_date(sid) == "2026-10-22"         # у неё ещё 22-е
    assert db.get_date(other) == "2026-10-23"       # у бишкекца уже 23-е
    assert db.in_night_tail(sid) is True


def test_riyadh_evening_is_her_today(test_db, monkeypatch):
    sid, _ = _student("Ханума", "800", "Asia/Riyadh")
    at(monkeypatch, 2, 30, day=23, month=10)        # 02:30 Бишкек = 23:30 Эр-Рияд 22-го
    assert db.get_date(sid) == "2026-10-22"
    assert db.in_night_tail(sid) is False           # для неё это вечер, не ночь


def test_context_of_writer_and_group_date(test_db, monkeypatch):
    _student("Ханума", "800", "Asia/Riyadh")
    at(monkeypatch, 4, 23, day=23, month=10)
    assert db.get_date() == "2026-10-23"
    with db.day_of("800"):
        assert db.get_date() == "2026-10-22"
        assert db.group_date() == "2026-10-23"      # группа живёт по Бишкеку
    assert db.get_date() == "2026-10-23"


def test_unknown_or_bad_tz_falls_back_to_bishkek(test_db, monkeypatch):
    sid, _ = _student("Без пояса", "802")
    with db.db() as c:
        c.execute("UPDATE users SET tz='Mars/Olympus' WHERE id=?", (sid,))
    at(monkeypatch, 4, 23, day=23, month=10)
    assert db.get_date(sid) == "2026-10-23"
    with db.day_of("999999"):
        assert db.get_date() == "2026-10-23"


def test_her_open_day_is_not_a_skip(test_db, monkeypatch):
    """Сдала 22-го вечером по Эр-Рияду; в 04:23 Бишкека её 22-е ещё идёт -
    пропусков у неё ноль, а не один."""
    sid, g = _student("Ханума", "800", "Asia/Riyadh")
    with db.db() as c:
        c.execute("UPDATE user_groups SET joined_date='2026-10-01' WHERE user_id=?", (sid,))
    db.save_report(sid, g["id"], "2026-10-22", {"m": True, "r": True, "t": True})
    at(monkeypatch, 4, 23, day=23, month=10)
    assert db.get_days_since_last_report(sid, g["id"]) == 0


def test_all_days_closed_waits_for_westernmost(test_db, monkeypatch):
    _student("Париж", "803", "Europe/Paris")        # 26.10 уже зимнее UTC+1
    at(monkeypatch, 7, 30, day=27, month=10)        # 07:30 Бишкек = 02:30 Париж
    assert db.all_days_closed("2026-10-26") is False
    at(monkeypatch, 8, 1, day=27, month=10)         # 08:01 Бишкек = 03:01 Париж
    assert db.all_days_closed("2026-10-26") is True


def test_all_days_closed_bishkek_only(test_db, monkeypatch):
    _student("Бишкек", "801")
    at(monkeypatch, 3, 1, day=27, month=10)
    assert db.all_days_closed("2026-10-26") is True
    at(monkeypatch, 2, 59, day=27, month=10)
    assert db.all_days_closed("2026-10-26") is False
