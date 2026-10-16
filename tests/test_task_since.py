"""Новое задание не обнуляет серию задним числом (16.10.2026).

Живой случай: 15.10 программа включила таджвид («j») 7 женским и 6 мужским
группам; серия меряла все прошлые дни по новому списку m,r,t,j - дни без «j»
стали неполными, у 40 сестёр и 11 братьев серия упала в 1 (до 43 дней).
"""
from datetime import date, timedelta

import core.db as db


def _day(d):
    return d.isoformat()


def _group_with_history(today, days=10):
    db.save_group("-100961", "G-J", tasks="m,r,t")
    g = db.get_group("-100961")
    sid = db.add_student("Сестра", g["id"], phone="961961")
    for i in range(days, 1, -1):                      # до позавчера - m,r,t
        db.save_report(sid, g["id"], _day(today - timedelta(days=i)), {k: True for k in "mrt"})
    return g, sid


def _enable_j(g, on_day, monkeypatch):
    monkeypatch.setattr(db, "get_date", lambda: _day(on_day))
    db.update_group_tasks(g["chat_id"], "m,r,t,j")
    return db.get_group(g["chat_id"])


def test_new_task_keeps_past_streak(test_db, monkeypatch):
    today = date(2026, 10, 16)
    g, sid = _group_with_history(today)
    g = _enable_j(g, today - timedelta(days=1), monkeypatch)
    db.save_report(sid, g["id"], _day(today - timedelta(days=1)), {k: True for k in "mrtj"})
    tasks = db.get_group_tasks(g)
    yesterday = _day(today - timedelta(days=1))
    assert db.get_streak_days(sid, g["id"], tasks, for_date=yesterday) == 10
    assert db.get_group_streaks(g["id"], tasks, for_date=yesterday)[sid] == 10


def test_new_task_required_from_its_day(test_db, monkeypatch):
    today = date(2026, 10, 16)
    g, sid = _group_with_history(today)
    g = _enable_j(g, today - timedelta(days=1), monkeypatch)
    db.save_report(sid, g["id"], _day(today - timedelta(days=1)), {k: True for k in "mrt"})
    tasks = db.get_group_tasks(g)
    yesterday = _day(today - timedelta(days=1))
    assert db.get_streak_days(sid, g["id"], tasks, for_date=yesterday) == 0
    assert sid not in db.get_group_streaks(g["id"], tasks, for_date=yesterday)


def test_early_trainer_task_does_not_count_before_since(test_db, monkeypatch):
    """«j» в добровольном тренажёре до включения не мешает и не нужен."""
    today = date(2026, 10, 16)
    g, sid = _group_with_history(today, days=3)
    db.save_report(sid, g["id"], _day(today - timedelta(days=3)), {"j": True})
    g = _enable_j(g, today - timedelta(days=1), monkeypatch)
    db.save_report(sid, g["id"], _day(today - timedelta(days=1)), {k: True for k in "mrtj"})
    tasks = db.get_group_tasks(g)
    yesterday = _day(today - timedelta(days=1))
    assert db.get_streak_days(sid, g["id"], tasks, for_date=yesterday) == 3
    assert db.get_group_streaks(g["id"], tasks, for_date=yesterday)[sid] == 3


def test_removed_task_forgets_since(test_db, monkeypatch):
    today = date(2026, 10, 16)
    g, sid = _group_with_history(today)
    g = _enable_j(g, today, monkeypatch)
    assert db.task_since(g["id"]) == {"j": _day(today)}
    db.update_group_tasks(g["chat_id"], "m,r,t")
    assert db.task_since(g["id"]) == {}


def test_tasks_on():
    since = {"j": "2026-10-15"}
    assert db.tasks_on(["m", "r", "t", "j"], since, "2026-10-14") == ["m", "r", "t"]
    assert db.tasks_on(["m", "r", "t", "j"], since, "2026-10-15") == ["m", "r", "t", "j"]
