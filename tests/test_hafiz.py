"""Хафиз (26.09.2026): заучивание не обязательно - полный день без m."""
import core.db as db


def _group():
    db.save_group("-100901", "N-1", tasks="m,r,t,j,n,h")
    db.update_group_type("-100901", "pro")
    return db.get_group("-100901")


def _submit(uid, gid, date, tasks):
    db.save_report(uid, gid, date, {k: True for k in tasks})


def test_hafiz_full_day_without_memorization(test_db):
    g = _group()
    tasks = db.get_group_tasks(g)
    db.add_student("Имран", g["id"], phone="h1")
    db.add_student("Обычный", g["id"], phone="s1")
    h = db.find_by_phone("h1", g["id"])
    s = db.find_by_phone("s1", g["id"])
    db.set_hafiz(h["id"])
    today = db.get_date()
    _submit(h["id"], g["id"], today, "rtjnh")
    _submit(s["id"], g["id"], today, "rtjnh")

    assert db.get_streak_days(h["id"], g["id"], tasks) == 1
    assert db.get_streak_days(s["id"], g["id"], tasks) == 0
    assert db.get_group_streaks(g["id"], tasks) == {h["id"]: 1}
    missing = {st["id"]: m for st, m in db.get_missing_students(g["id"], tasks)}
    assert h["id"] not in missing and missing[s["id"]] == ["m"]
    full = {c["id"]: c["full"] for c in db.get_daily_task_counts(g["id"], tasks, today)}
    assert full == {h["id"]: True, s["id"]: False}
    report = db.format_daily_report(g["id"], "N-1", tasks, today)
    assert "Имран: ➖✅✅✅✅✅ 5/5 🎉" in report


def test_hafiz_still_needs_other_tasks_and_m_counts(test_db):
    """m сверх нормы не заменяет недостающее задание."""
    g = _group()
    tasks = db.get_group_tasks(g)
    db.add_student("Имран", g["id"], phone="h1")
    h = db.find_by_phone("h1", g["id"])
    db.set_hafiz(h["id"])
    _submit(h["id"], g["id"], db.get_date(), "mrtjn")   # без хадиса
    assert db.get_streak_days(h["id"], g["id"], tasks) == 0
    assert [m for _, m in db.get_missing_students(g["id"], tasks)] == [["h"]]
    db.set_hafiz(h["id"], False)
    assert db.student_tasks(h["id"], tasks) == tasks
