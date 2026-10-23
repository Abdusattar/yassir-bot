"""Равные баллы - одно место (23.10.2026).

Мохинур (женская, группа Мохидил): 42 балла за 12-18.10, как у пятерых из
топа, но в «Топ-10 недели» не попала - список резался на 10-м по порядку
строк из базы. В /rating у неё и Aisha было по 37, а медали 🥇 и 🥈. В
«Примеры недели» из группы не вошёл никто: хадис открылся 15.10, а каждый
день мерился сегодняшним набором заданий.
"""
from datetime import date

import core.db as db
import core.scheduler as sch


def test_places_are_dense_and_shared():
    items = [("А", 45), ("Б", 42), ("В", 45), ("Г", 30), ("Д", 42)]
    places = db.places_by_score(items, lambda x: x[1])
    assert [(p, s, sorted(n for n, _ in g)) for p, s, g in places] == [
        (1, 45, ["А", "В"]), (2, 42, ["Б", "Д"]), (3, 30, ["Г"])]
    assert db.place_mark(1) == "🥇" and db.place_mark(4) == "4."
    assert db.place_of(items, lambda x: x[1], lambda x: x[0] == "Д") == 2


def _points(sid, gid, day, pts, cat="task", sub="m"):
    with db.db() as c:
        c.execute("INSERT INTO score_events(student_id, group_id, date, category, subcategory, points)"
                  " VALUES(?,?,?,?,?,?)", (sid, gid, day, cat, sub, pts))


def test_period_report_puts_equal_scores_on_one_line(test_db):
    db.save_group("-100801", "Группа 1 устаза Мохидил")
    g = db.get_group("-100801")
    a = db.add_student("Aisha", g["id"], phone="801")
    m = db.add_student("Мохинур", g["id"], phone="802")
    s = db.add_student("Asaliya", g["id"], phone="803")
    today = db.get_date()
    # Отчёт считает задания штуками, остальное - бонусами.
    _points(a, g["id"], today, 37, cat="attendance", sub="online")
    _points(m, g["id"], today, 37, cat="attendance", sub="online")
    _points(s, g["id"], today, 36, cat="attendance", sub="online")
    report = db.format_period_report(g["id"], "Группа 1", ["m"], 7)
    first = next(l for l in report.splitlines() if l.startswith("🥇"))
    assert "Aisha" in first and "Мохинур" in first and "37" in first
    assert any(l.startswith("🥈") and "Asaliya" in l for l in report.splitlines())


def test_weekly_top_does_not_cut_a_tie(test_db, monkeypatch):
    monkeypatch.setattr(sch, "SUPER_ADMIN_IDS", [])
    db.save_group("-100802", "Группа Т")
    g = db.get_group("-100802")
    with db.db() as c:
        c.execute("UPDATE groups SET group_type='pro' WHERE id=?", (g["id"],))
    for i in range(5):
        _points(db.add_student("Сорок пять %d" % i, g["id"], phone="81%d" % i), g["id"], "2026-10-14", 45)
    for i in range(6):
        _points(db.add_student("Сорок два %d" % i, g["id"], phone="82%d" % i), g["id"], "2026-10-14", 42)
    top = sch._top_students_by_points("2026-10-12", "2026-10-18", 10)
    assert [(p, pts, len(people)) for p, pts, people in top] == [(1, 45, 5), (2, 42, 6)]


def test_full_week_measures_each_day_by_tasks_open_that_day(test_db, monkeypatch):
    monkeypatch.setattr(sch, "SUPER_ADMIN_IDS", [])
    db.save_group("-100803", "Группа Х", tasks="m,r")
    g = db.get_group("-100803")
    with db.db() as c:
        c.execute("UPDATE groups SET group_type='pro' WHERE id=?", (g["id"],))
        c.execute("INSERT INTO group_task_since(group_id, task, since) VALUES(?,?,?)",
                  (g["id"], "j", "2026-10-15"))
        c.execute("UPDATE groups SET tasks='m,r,j' WHERE id=?", (g["id"],))
    sid = db.add_student("Мохинур", g["id"], phone="830")
    for d in range(12, 19):
        day = "2026-10-%02d" % d
        for k in ("m", "r") + (("j",) if d >= 15 else ()):
            _points(sid, g["id"], day, 1, sub=k)
    names = sch._full_period_students(date(2026, 10, 12), date(2026, 10, 18))
    assert ("Мохинур", "Группа Х") in names
