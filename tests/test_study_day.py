"""Учебный день кончается в три ночи, а не в полночь (20.09.2026).

Жалоба пользователя: «у студента не было пропуска, а бот пишет, что есть».
Разбор на проде показал причину: зачёт писался на календарную дату Бишкека,
и тот, кто садится за задания поздно вечером, перешагивал полночь - сдача
уезжала в следующий день, а прошедший оставался пустым и считался пропуском.
За сентябрь так потеряли дни 26 человек из 195 (37 дней); у одного брата
сдачи идут в 23:48-02:58 каждый день.

Решение пользователя: день студента закрывается в 03:00. Здесь проверяется
сама точка отсчёта и то, что счёт пропусков считает по ней же.
"""
from datetime import datetime, timedelta

import pytest
import pytz

import core.db as db


TZ = pytz.timezone(db.TZ)


def at(monkeypatch, hh, mm=0, day=15, month=9, year=2026):
    """Подменяем «сейчас» в Бишкеке. Патчим datetime целиком в core.db:
    get_date считает от него, а не от отдельной функции."""
    moment = TZ.localize(datetime(year, month, day, hh, mm))

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return moment.astimezone(tz) if tz else moment.replace(tzinfo=None)

    monkeypatch.setattr(db, "datetime", FrozenDatetime)
    return moment


# ── Сама граница ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("hh,mm,expect", [
    (21, 0, "2026-09-15"),      # вечер - свой день
    (23, 59, "2026-09-15"),     # без минуты полночь - всё ещё свой
    (0, 1, "2026-09-15"),       # минута после полуночи - ВЧЕРАШНИЙ день
    (2, 59, "2026-09-15"),      # без минуты три - ещё вчерашний
    (3, 0, "2026-09-15"),       # ровно три: сдвиг даёт предыдущие сутки в 00:00
    (3, 1, "2026-09-15"),       # начало нового учебного дня наступает здесь
    (9, 0, "2026-09-15"),       # день как день
])
def test_study_date_shifts_until_three_at_night(monkeypatch, hh, mm, expect):
    at(monkeypatch, hh, mm)
    # 15 сентября 00:01 - это ещё 14-е; для наглядности считаем от 15-го.
    day = 15 if hh >= 3 else 16
    at(monkeypatch, hh, mm, day=day)
    assert db.get_date() == expect


def test_calendar_date_stays_calendar(monkeypatch):
    """Календарь никуда не съезжает: он нужен всему, что живёт не по
    учебному дню - расписанию, срокам, отчётам «за такое-то число»."""
    at(monkeypatch, 1, 30, day=16)
    assert db.get_calendar_date() == "2026-09-16"
    assert db.get_date() == "2026-09-15"


def test_night_tail_flag(monkeypatch):
    at(monkeypatch, 1, 30, day=16)
    assert db.in_night_tail() is True
    at(monkeypatch, 21, 0, day=15)
    assert db.in_night_tail() is False


def test_day_is_still_twenty_four_hours(monkeypatch):
    """Сдвиг не добавляет и не съедает сутки: за 24 часа ровно одна смена."""
    seen = set()
    start = TZ.localize(datetime(2026, 9, 15, 3, 30))
    for i in range(24):
        moment = start + timedelta(hours=i)
        at(monkeypatch, moment.hour, moment.minute, day=moment.day)
        seen.add(db.get_date())
    assert seen == {"2026-09-15"}


# ── Ради чего всё: ночная сдача не оставляет пустого дня ───────────────────

CHAT = "-100777001"
PHONE = "777001"


@pytest.fixture
def student(test_db):
    db.save_group(CHAT, "G-9", tasks="m,r,t")
    db.update_group_type(CHAT, "pro")
    group = db.get_group(CHAT)
    db.add_student("Ибрахим", group["id"], phone=PHONE)
    return {"group": group, "student": db.find_by_phone(PHONE, group["id"])}


def _joined_first_of_month(group_id, phone="777002"):
    """Студент, заведённый под замороженным временем. Важно: окна пропусков
    отсчитываются от users.added_date / user_groups.joined_date, и человек,
    созданный «настоящим сегодня», обрывает любой цикл на первом шаге —
    тест тогда проходит при любом поведении."""
    db.add_student("Ибрахим", group_id, phone=phone)
    return db.find_by_phone(phone, group_id)["id"]


def test_late_night_submission_belongs_to_the_evening(student, monkeypatch):
    """Случай с прода: сдал в 23:57, доделал в 00:15 - это один вечер, а не
    два разных дня, из которых один потом считается пропущенным."""
    at(monkeypatch, 23, 57, day=15)
    db.save_report(student["student"]["id"], student["group"]["id"], db.get_date(), {"m": True})

    at(monkeypatch, 0, 15, day=16)
    db.save_report(student["student"]["id"], student["group"]["id"], db.get_date(), {"r": True})

    with db.db() as c:
        rows = c.execute(
            "SELECT date, subcategory FROM score_events WHERE student_id=? ORDER BY subcategory",
            (student["student"]["id"],)).fetchall()
    assert [(r["date"], r["subcategory"]) for r in rows] == [
        ("2026-09-15", "m"), ("2026-09-15", "r")]


def test_after_three_a_new_day_starts(student, monkeypatch):
    """Три ночи - уже новый день, иначе «вчера» тянулось бы до утра."""
    at(monkeypatch, 23, 50, day=15)
    db.save_report(student["student"]["id"], student["group"]["id"], db.get_date(), {"m": True})

    at(monkeypatch, 3, 30, day=16)
    db.save_report(student["student"]["id"], student["group"]["id"], db.get_date(), {"m": True})

    with db.db() as c:
        dates = [r["date"] for r in c.execute(
            "SELECT DISTINCT date FROM score_events WHERE student_id=? ORDER BY date",
            (student["student"]["id"],)).fetchall()]
    assert dates == ["2026-09-15", "2026-09-16"]


def test_today_report_reads_the_same_day(student, monkeypatch):
    """Экран «Мой день» и зачёт обязаны смотреть на одну дату: в час ночи
    человек видит вчерашние отметки, и это правильно - день ещё идёт."""
    at(monkeypatch, 22, 0, day=15)
    db.save_report(student["student"]["id"], student["group"]["id"], db.get_date(), {"m": True})

    at(monkeypatch, 1, 0, day=16)
    report = db.get_today_report(student["student"]["id"], student["group"]["id"])

    assert report and report["m"] is True


def test_night_submission_does_not_leave_an_empty_day(student, monkeypatch):
    """Прямая проверка жалобы: сдавал каждый вечер, перешагивая полночь -
    пропусков быть не должно."""
    for day in (11, 12, 13, 14):
        at(monkeypatch, 23, 40, day=day)
        db.save_report(student["student"]["id"], student["group"]["id"], db.get_date(),
                       {"m": True, "r": True, "t": True})
        at(monkeypatch, 0, 20, day=day + 1)     # доделал уже за полночь
        db.save_report(student["student"]["id"], student["group"]["id"], db.get_date(),
                       {"t": True})

    at(monkeypatch, 12, 0, day=15)
    detail = db.get_skip_count_month_detail(student["student"]["id"], student["group"]["id"])

    # Окно считается от вступления в группу, поэтому проверяем именно дни
    # 11-14: все четыре закрыты, пустых среди них нет.
    with db.db() as c:
        dates = {r["date"] for r in c.execute(
            "SELECT DISTINCT date FROM score_events WHERE student_id=?",
            (student["student"]["id"],)).fetchall()}
    assert {"2026-09-11", "2026-09-12", "2026-09-13", "2026-09-14"} <= dates
    assert "2026-09-15" not in dates            # сегодняшний ещё не сдан
    assert detail["missed"] == detail["total"] - len(
        [d for d in dates if detail["start"] <= d <= detail["end"]])


def test_open_day_is_not_counted_as_a_skip_at_night(student, monkeypatch):
    """Находка 20.09: get_date() сдвинулся, а окна пропусков брали
    КАЛЕНДАРНОЕ «сегодня» — и в час ночи ещё идущий учебный день уже попадал
    в окно как прошедший. Человек, который сядет за задания в два ночи, к
    тому моменту уже числился пропустившим."""
    at(monkeypatch, 12, 0, day=1)
    uid = _joined_first_of_month(student["group"]["id"])
    for day in (11, 12, 13, 14):
        at(monkeypatch, 22, 0, day=day)
        db.save_report(uid, student["group"]["id"], db.get_date(),
                       {"m": True, "r": True, "t": True})

    at(monkeypatch, 12, 0, day=15)
    by_day = db.get_skip_count_month_detail(uid, student["group"]["id"])
    at(monkeypatch, 1, 0, day=16)            # тот же учебный день, но за полночь
    by_night = db.get_skip_count_month_detail(uid, student["group"]["id"])

    assert by_night == by_day                      # окно то же самое
    assert by_night["end"] == "2026-09-14"       # текущий день в счёт не идёт


def test_days_since_last_report_counts_by_study_day(student, monkeypatch):
    """Сдал вечером — в час ночи «дней без сдачи» ноль, а не один. Иначе
    ночному студенту прилетало бы «три дня не сдаёшь» на день раньше срока
    (core/scheduler.py: personal_reminders)."""
    at(monkeypatch, 12, 0, day=1)
    uid = _joined_first_of_month(student["group"]["id"])
    at(monkeypatch, 23, 30, day=15)
    db.save_report(uid, student["group"]["id"], db.get_date(), {"m": True})

    at(monkeypatch, 1, 0, day=16)

    assert db.get_days_since_last_report(uid, student["group"]["id"]) == 0
