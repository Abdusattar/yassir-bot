import pytest
from core.db import (
    save_group, get_group, add_student, get_students,
    find_by_phone, find_by_name, register_student, deactivate_student,
    save_report, get_today_report, get_streak_days, get_skip_count_month,
    add_bonus, get_date,
)


# ── Группы ────────────────────────────────────────────────────────────────────

def test_save_and_get_group(test_db):
    save_group("-100111", "Тестовая группа", tasks="m,r,t")
    g = get_group("-100111")
    assert g is not None
    assert g["title"] == "Тестовая группа"
    assert g["tasks"] == "m,r,t"


def test_get_group_not_found(test_db):
    assert get_group("-999999") is None


# ── Студенты ──────────────────────────────────────────────────────────────────

def test_add_and_get_students(test_db):
    save_group("-100222", "Группа А")
    g = get_group("-100222")
    add_student("Бакыт", g["id"])
    students = get_students(g["id"])
    assert len(students) == 1
    assert students[0]["name"] == "Бакыт"


def test_find_by_phone(test_db):
    save_group("-100333", "Группа Б")
    g = get_group("-100333")
    sid = add_student("Азамат", g["id"], phone="111222333")
    found = find_by_phone("111222333", g["id"])
    assert found is not None
    assert found["name"] == "Азамат"


def test_find_by_phone_not_found(test_db):
    save_group("-100334", "Группа В")
    g = get_group("-100334")
    assert find_by_phone("000000000", g["id"]) is None


def test_find_by_name(test_db):
    save_group("-100335", "Группа Г")
    g = get_group("-100335")
    add_student("Закир", g["id"])
    found = find_by_name("Закир", g["id"])
    assert found is not None


def test_register_student_sets_phone(test_db):
    save_group("-100336", "Группа Д")
    g = get_group("-100336")
    sid = add_student("Нурлан", g["id"])
    register_student(sid, "555666777")
    found = find_by_phone("555666777", g["id"])
    assert found is not None
    assert found["name"] == "Нурлан"


def test_deactivate_student(test_db):
    save_group("-100337", "Группа Е")
    g = get_group("-100337")
    sid = add_student("Тимур", g["id"], phone="333444555")
    deactivate_student(sid)
    assert find_by_phone("333444555", g["id"]) is None


# ── Отчёты ────────────────────────────────────────────────────────────────────

def test_save_and_get_today_report(test_db):
    save_group("-100444", "Группа Ж")
    g = get_group("-100444")
    sid = add_student("Алибек", g["id"], phone="777888999")
    today = get_date()
    save_report(sid, g["id"], today, {"m": True, "r": True, "t": False})
    rep = get_today_report(sid)
    assert rep is not None
    assert rep["m"] == 1
    assert rep["r"] == 1
    assert rep["t"] == 0


def test_streak_zero_for_new_student(test_db):
    save_group("-100555", "Группа З")
    g = get_group("-100555")
    sid = add_student("Мирлан", g["id"])
    assert get_streak_days(sid) == 0


def test_streak_one_day(test_db):
    save_group("-100556", "Группа И")
    g = get_group("-100556")
    sid = add_student("Санжар", g["id"])
    save_report(sid, g["id"], get_date(), {"m": True, "r": True, "t": True})
    assert get_streak_days(sid) == 1


def test_skip_count_zero_for_new_student(test_db):
    save_group("-100557", "Группа К")
    g = get_group("-100557")
    sid = add_student("Руслан", g["id"])
    assert get_skip_count_month(sid) == 0


# ── Бонусы ────────────────────────────────────────────────────────────────────

def test_add_bonus(test_db):
    from core.db import db
    save_group("-100666", "Группа Л")
    g = get_group("-100666")
    sid = add_student("Данияр", g["id"])
    add_bonus(sid, g["id"], get_date(), 10, "тест")
    with db() as c:
        row = c.execute("SELECT SUM(points) as total FROM bonus_points WHERE sid=?", (sid,)).fetchone()
    assert row["total"] == 10
