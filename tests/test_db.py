import pytest
from core.db import (
    save_group, get_group, add_student, get_students,
    find_by_phone, find_by_name, register_student, deactivate_student,
    save_report, get_today_report, get_streak_days, get_skip_count_month,
    add_bonus, get_date, count_report_days_since,
    get_or_create_attendance_confirm, add_attendance_confirm_student,
    get_attendance_confirm_by_id, get_attendance_confirm_students,
    set_attendance_confirm_decision, get_stale_attendance_confirms,
    mark_attendance_confirm_escalated,
    get_users_due_for_survey, start_survey, get_survey_stage,
    save_survey_location, save_survey_age, mark_dm_ok_by_phone, db,
    add_group_admin,
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


def test_count_report_days_since_ignores_partial_days(test_db):
    """12.08.2026: раньше день засчитывался в prep-порог с ЛЮБЫМ одним
    заданием - лазейка, противоречившая решению устаза (все три
    обязательны с первого дня). Теперь тот же строгий критерий, что у
    стрика."""
    save_group("-100560", "Группа Н", tasks="m,r,t")
    g = get_group("-100560")
    sid = add_student("Азим", g["id"])
    save_report(sid, g["id"], get_date(), {"m": True, "r": False, "t": False})
    assert count_report_days_since(sid, g["id"], get_date()) == 0


def test_count_report_days_since_counts_full_days(test_db):
    from datetime import timedelta
    from core.db import get_now
    save_group("-100561", "Группа О", tasks="m,r,t")
    g = get_group("-100561")
    sid = add_student("Бахтияр", g["id"])
    yesterday = (get_now() - timedelta(days=1)).date().isoformat()
    save_report(sid, g["id"], yesterday, {"m": True, "r": True, "t": True})
    save_report(sid, g["id"], get_date(), {"m": True, "r": True, "t": True})
    assert count_report_days_since(sid, g["id"], yesterday) == 2


def test_count_report_days_since_respects_lower_bound(test_db):
    from datetime import timedelta
    from core.db import get_now
    save_group("-100562", "Группа П", tasks="m,r,t")
    g = get_group("-100562")
    sid = add_student("Умар", g["id"])
    old_day = (get_now() - timedelta(days=20)).date().isoformat()
    save_report(sid, g["id"], old_day, {"m": True, "r": True, "t": True})
    save_report(sid, g["id"], get_date(), {"m": True, "r": True, "t": True})
    assert count_report_days_since(sid, g["id"], get_date()) == 1


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


# ── Анкета "откуда и сколько лет" ───────────────────────────────────────────────

def _make_survey_candidate(test_db, phone="700111", days_ago=30, dm_ok=1):
    save_group("-100790", "Группа С")
    g = get_group("-100790")
    sid = add_student("Гульнара", g["id"], phone=phone)
    with db() as c:
        c.execute(
            "UPDATE users SET added_date=date('now', ?), dm_ok=? WHERE id=?",
            (f"-{days_ago} days", dm_ok, sid)
        )
    return sid


def test_get_users_due_for_survey_includes_eligible(test_db):
    _make_survey_candidate(test_db, phone="700111", days_ago=31, dm_ok=1)
    due = get_users_due_for_survey()
    assert [r["phone"] for r in due] == ["700111"]


def test_get_users_due_for_survey_excludes_too_recent(test_db):
    _make_survey_candidate(test_db, phone="700112", days_ago=10, dm_ok=1)
    assert get_users_due_for_survey() == []


def test_get_users_due_for_survey_excludes_dm_not_ok(test_db):
    _make_survey_candidate(test_db, phone="700113", days_ago=31, dm_ok=0)
    assert get_users_due_for_survey() == []


def test_get_users_due_for_survey_excludes_already_started(test_db):
    _make_survey_candidate(test_db, phone="700114", days_ago=31, dm_ok=1)
    start_survey("700114")
    assert get_users_due_for_survey() == []


def test_survey_flow_location_then_age(test_db):
    _make_survey_candidate(test_db, phone="700115", days_ago=31, dm_ok=1)
    assert get_survey_stage("700115") is None

    start_survey("700115")
    assert get_survey_stage("700115") == "asked_location"

    save_survey_location("700115", "Бишкек")
    assert get_survey_stage("700115") == "asked_age"

    save_survey_age("700115", "22")
    assert get_survey_stage("700115") == "done"

    with db() as c:
        row = c.execute(
            "SELECT survey_location, survey_age FROM users WHERE phone=?", ("700115",)
        ).fetchone()
    assert row["survey_location"] == "Бишкек"
    assert row["survey_age"] == "22"


def test_get_users_due_for_survey_excludes_group_admin(test_db):
    """Устаз, который сам тоже студент где-то (30+ дней, dm_ok=1) - не должен
    попадать в анкету, иначе его следующий вопрос боту перехватится как
    ответ на survey_location (13.08.2026, найдено эдвайзери)."""
    save_group("-100791", "Группа Т")
    g1 = get_group("-100791")
    save_group("-100792", "Группа У")
    g2 = get_group("-100792")
    sid = add_student("Умар", g1["id"], phone="700116")
    add_group_admin(g2["id"], "700116")
    with db() as c:
        c.execute(
            "UPDATE users SET added_date=date('now', '-31 days'), dm_ok=1 WHERE id=?",
            (sid,)
        )
    assert get_users_due_for_survey() == []


def test_get_users_due_for_survey_respects_limit(test_db):
    save_group("-100793", "Группа Ф")
    g = get_group("-100793")
    for i in range(7):
        sid = add_student(f"Студент{i}", g["id"], phone=f"70012{i}")
        with db() as c:
            c.execute(
                "UPDATE users SET added_date=date('now', '-31 days'), dm_ok=1 WHERE id=?",
                (sid,)
            )
    assert len(get_users_due_for_survey(limit=3)) == 3
    assert len(get_users_due_for_survey(limit=100)) == 7
