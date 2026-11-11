"""Цвет дня в «Моём месяце» и у устаза (11.11.2026).

Повод - Розалина (группа 2 Мохидил, 4 задания): 7.11 сдала 3 из 4, а
календарь горел тёмно-зелёным, как полный день - цвет считал «3 и больше =
всё». Теперь сервер отдаёт, сколько обязательных не хватило по дню
(day_missing), и цвет идёт от этого.
"""
import core.db as db


def _group(tasks):
    db.save_group("-100902", "Группа 2", tasks=tasks)
    return db.get_group("-100902")


def _submit(uid, gid, date, tasks):
    db.save_report(uid, gid, date, {k: True for k in tasks})


def test_три_из_четырёх_не_полный_день(test_db):
    g = _group("m,r,t,j")
    db.add_student("Розалина", g["id"], phone="r1")
    s = db.find_by_phone("r1", g["id"])
    today = db.get_date()
    _submit(s["id"], g["id"], today, "mrj")
    days = db.get_student_month_days(s["id"], g["id"])
    assert db.day_missing(s["id"], g["id"], days, db.get_group_tasks(g)) == {today: 1}
    prog = {st["id"]: st for st in db.get_group_month_progress(g["id"])}
    assert prog[s["id"]]["miss"] == {today: 1}, "у устаза та же картина"


def test_шесть_заданий_и_хафиз(test_db):
    g = _group("m,r,t,j,n,h")
    db.add_student("Обычный", g["id"], phone="s1")
    db.add_student("Хафиз", g["id"], phone="h1")
    s = db.find_by_phone("s1", g["id"])
    h = db.find_by_phone("h1", g["id"])
    db.set_hafiz(h["id"])
    today = db.get_date()
    _submit(s["id"], g["id"], today, "rtjnh")      # 5 из 6
    _submit(h["id"], g["id"], today, "rtjnh")      # хафизу заучивание не нужно
    tasks = db.get_group_tasks(g)
    assert db.day_missing(s["id"], g["id"], db.get_student_month_days(s["id"], g["id"]), tasks) == {today: 1}
    assert db.day_missing(h["id"], g["id"], db.get_student_month_days(h["id"], g["id"]), tasks) == {today: 0}


def test_задание_добавленное_позже_не_портит_ранние_дни(test_db):
    g = _group("m,r,t")
    db.add_student("Студент", g["id"], phone="s2")
    s = db.find_by_phone("s2", g["id"])
    early = "2026-11-01"
    _submit(s["id"], g["id"], early, "mrt")
    # таджвид обязателен только со 2-го
    with db.db() as c:
        c.execute("INSERT INTO group_task_since(group_id, task, since) VALUES(?,?,?)", (g["id"], "j", "2026-11-02"))
    miss = db.day_missing(s["id"], g["id"], {early: ["m", "r", "t"], "2026-11-03": ["m", "r", "t"]},
                          ["m", "r", "t", "j"])
    assert miss == {early: 0, "2026-11-03": 1}
