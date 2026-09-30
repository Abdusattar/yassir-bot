"""Серия идёт через перевод в другую группу (30.09.2026).

Живой случай - Эрлан (мужской бот): без единого пропуска с 23.08 -
подготовительная, G-6, с 26.09 N-2a («про»). Серия считалась только по
group_id текущей группы, и после перехода бот показал 4 вместо 38; недельный
бонус за неделю перехода не дали ни в старой, ни в новой группе.
"""
from datetime import date, timedelta

import core.db as db


def _day(d):
    return d.isoformat()


def _full(sid, gid, d, tasks):
    db.save_report(sid, gid, _day(d), {k: True for k in tasks})


def _moved_student(today):
    db.save_group("-100951", "Old G", tasks="m,r,t")
    db.update_group_type("-100951", "relaxed")
    db.save_group("-100952", "New Pro", tasks="m,r,t,j,n")
    db.update_group_type("-100952", "pro")
    old, new = db.get_group("-100951"), db.get_group("-100952")
    sid = db.add_student("Переведённый", old["id"], phone="951951")
    moved_on = today - timedelta(days=4)
    for i in range(10, 3, -1):                       # 10..4 дней назад - старая группа
        _full(sid, old["id"], today - timedelta(days=i), "mrt")
    db.deactivate_student(sid, old["id"])
    db.add_student("Переведённый", new["id"], phone="951951")
    with db.db() as c:
        c.execute("UPDATE user_groups SET joined_date=? WHERE user_id=? AND group_id=?",
                  (_day(moved_on), sid, new["id"]))
        c.execute("UPDATE user_groups SET joined_date=? WHERE user_id=? AND group_id=?",
                  (_day(today - timedelta(days=20)), sid, old["id"]))
    for i in range(3, 0, -1):                        # 3..1 дня назад - новая группа
        _full(sid, new["id"], today - timedelta(days=i), "mrtjn")
    return sid, old, new


def test_streak_continues_through_transfer(test_db):
    today = date(2026, 9, 30)
    sid, old, new = _moved_student(today)
    tasks = db.get_group_tasks(new)
    assert db.get_streak_days(sid, new["id"], tasks, for_date=_day(today - timedelta(days=1))) == 10
    assert db.get_group_streaks(new["id"], tasks, for_date=_day(today - timedelta(days=1)))[sid] == 10


def test_gap_before_transfer_still_breaks(test_db):
    today = date(2026, 9, 30)
    sid, old, new = _moved_student(today)
    with db.db() as c:
        c.execute("DELETE FROM score_events WHERE student_id=? AND date=?",
                  (sid, _day(today - timedelta(days=6))))
    tasks = db.get_group_tasks(new)
    assert db.get_streak_days(sid, new["id"], tasks, for_date=_day(today - timedelta(days=1))) == 5


def test_tadabbur_does_not_borrow_history(test_db):
    today = date(2026, 9, 30)
    sid, old, new = _moved_student(today)
    db.save_group("-100953", "Tadabbur T", tasks="m,r,t")
    db.update_group_type("-100953", "tadabbur")
    tad = db.get_group("-100953")
    db.add_student("Переведённый", tad["id"], phone="951951")
    assert db.prior_full_dates(sid, tad["id"]) == set()
