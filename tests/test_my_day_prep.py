"""Полоса «Мой день» на дашборде у студента подготовительной (14.09.2026):
_my_day искал группу без include_prep, и у всей подготовительной полосы не
было."""

import core.db as db
import core.mufradat_api as api


def test_prep_student_gets_my_day(test_db):
    db.save_group("-100903", "Yassir подготовительная", tasks="m,r,t")
    db.update_group_type("-100903", "prep")
    g = db.get_group("-100903")
    sid = db.add_student("Акын", g["id"], phone="777")
    db.save_report(sid, g["id"], db.get_date(), {"m": True})

    day = api._dashboard_facts("777")["day"]
    assert day == {
        "tasks": [{"k": "m", "done": True}, {"k": "r", "done": False}, {"k": "t", "done": False}],
        "done": 1, "total": 3,
        # Хвост суток (20.09.2026): до трёх ночи идёт вчерашний учебный день,
        # и приложение подписывает это под полосой. Днём - False.
        "night": db.in_night_tail(),
    }
