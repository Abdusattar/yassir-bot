import pytest
from core.db import (
    save_group, get_group, add_student, get_students,
    find_by_phone, find_by_name, register_student, deactivate_student,
    save_report, get_today_report, get_streak_days, get_skip_count_month,
    add_bonus, get_date,
    get_or_create_attendance_confirm, add_attendance_confirm_student,
    get_attendance_confirm_by_id, get_attendance_confirm_students,
    set_attendance_confirm_decision, get_stale_attendance_confirms,
    mark_attendance_confirm_escalated,
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
    deactivate_student(sid, g["id"])
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
    assert get_streak_days(sid, g["id"], ["m", "r", "t"]) == 0


def test_streak_one_day(test_db):
    save_group("-100556", "Группа И")
    g = get_group("-100556")
    sid = add_student("Санжар", g["id"])
    save_report(sid, g["id"], get_date(), {"m": True, "r": True, "t": True})
    assert get_streak_days(sid, g["id"], ["m", "r", "t"]) == 1


def test_streak_broken_by_partial_day(test_db):
    """Строгое правило (07.08.2026): не все 3 задания в день - день не
    засчитывается в серию, даже если что-то сдано."""
    save_group("-100558", "Группа Л")
    g = get_group("-100558")
    sid = add_student("Нурлан", g["id"])
    save_report(sid, g["id"], get_date(), {"m": True, "r": True, "t": False})
    assert get_streak_days(sid, g["id"], ["m", "r", "t"]) == 0


def test_streak_grace_for_today_not_yet_reported(test_db):
    """Без явной даты (for_date=None) и без сегодняшнего отчёта серия не
    обнуляется - считается по вчерашний день включительно."""
    from datetime import timedelta
    from core.db import get_now
    save_group("-100559", "Группа М")
    g = get_group("-100559")
    sid = add_student("Ислам", g["id"])
    yesterday = (get_now() - timedelta(days=1)).date().isoformat()
    save_report(sid, g["id"], yesterday, {"m": True, "r": True, "t": True})
    assert get_streak_days(sid, g["id"], ["m", "r", "t"]) == 1


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
    add_bonus(sid, g["id"], get_date(), 10, "bonus", subcategory="тест")
    with db() as c:
        row = c.execute(
            "SELECT SUM(points) as total FROM score_events WHERE student_id=? AND category='bonus'",
            (sid,)
        ).fetchone()
    assert row["total"] == 10


# ── Подтверждение урока перед начислением баллов за "у" ────────────────────────

def test_attendance_confirm_dedup_same_day(test_db):
    """Первый студент за день создаёт запись, второй - переиспользует её."""
    save_group("-100777", "Группа М")
    g = get_group("-100777")
    sid1 = add_student("Амир", g["id"])
    sid2 = add_student("Рауф", g["id"])

    cid1, is_new1 = get_or_create_attendance_confirm(g["id"], "2026-07-31")
    add_attendance_confirm_student(cid1, sid1)
    assert is_new1 is True

    cid2, is_new2 = get_or_create_attendance_confirm(g["id"], "2026-07-31")
    add_attendance_confirm_student(cid2, sid2)
    assert is_new2 is False
    assert cid1 == cid2

    students = get_attendance_confirm_students(cid1)
    assert {s["id"] for s in students} == {sid1, sid2}


def test_attendance_confirm_different_days_separate_records(test_db):
    save_group("-100778", "Группа Н")
    g = get_group("-100778")
    cid1, is_new1 = get_or_create_attendance_confirm(g["id"], "2026-07-30")
    cid2, is_new2 = get_or_create_attendance_confirm(g["id"], "2026-07-31")
    assert cid1 != cid2
    assert is_new1 is True and is_new2 is True


def test_attendance_confirm_decision_defaults_to_none(test_db):
    save_group("-100779", "Группа О")
    g = get_group("-100779")
    cid, _ = get_or_create_attendance_confirm(g["id"], "2026-07-31")
    row = get_attendance_confirm_by_id(cid)
    assert row["decision"] is None
    assert row["escalated_at"] is None

    set_attendance_confirm_decision(cid, "yes")
    row = get_attendance_confirm_by_id(cid)
    assert row["decision"] == "yes"
    assert row["decided_at"] is not None


def test_attendance_confirm_stale_escalation(test_db):
    """Не решённые в течение N минут записи попадают в список на эскалацию,
    но только один раз - после mark_attendance_confirm_escalated не возвращаются снова."""
    from core.db import db
    save_group("-100780", "Группа П")
    g = get_group("-100780")
    cid, _ = get_or_create_attendance_confirm(g["id"], "2026-07-31")

    assert get_stale_attendance_confirms(30) == []

    with db() as c:
        c.execute(
            "UPDATE attendance_confirm SET asked_at=datetime('now','-40 minutes') WHERE id=?",
            (cid,)
        )

    stale = get_stale_attendance_confirms(30)
    assert len(stale) == 1
    assert stale[0]["id"] == cid

    mark_attendance_confirm_escalated(cid)
    assert get_stale_attendance_confirms(30) == []


def test_attendance_confirm_resolved_not_stale(test_db):
    """Решённая запись не должна эскалироваться, даже если "просрочена"."""
    from core.db import db
    save_group("-100781", "Группа Р")
    g = get_group("-100781")
    cid, _ = get_or_create_attendance_confirm(g["id"], "2026-07-31")
    set_attendance_confirm_decision(cid, "no")

    with db() as c:
        c.execute(
            "UPDATE attendance_confirm SET asked_at=datetime('now','-40 minutes') WHERE id=?",
            (cid,)
        )

    assert get_stale_attendance_confirms(30) == []
