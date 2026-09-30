"""След снятых баллов (30.09.2026, аудит бальной системы).

Раньше снятие было DELETE без следа: студентка спрашивает «куда делся балл» -
а ответить нечем. Теперь каждое снятие ложится в score_removals: что было,
кто снял и почему.
"""
import core.db as db


def _student():
    db.save_group("-100931", "Test Removals", tasks="m,r,t")
    g = db.get_group("-100931")
    sid = db.add_student("Снятая", g["id"], phone="931931")
    return sid, g


def _removals(sid):
    with db.db() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM score_removals WHERE student_id=? ORDER BY id", (sid,))]


def test_rejected_revision_leaves_trail(test_db):
    sid, g = _student()
    db.save_report(sid, g["id"], "2026-09-28", {"r": True})
    assert db.cancel_task_on(sid, g["id"], "2026-09-28", "r", by="555", why="запись отвергнута") is True
    rows = _removals(sid)
    assert len(rows) == 1
    assert rows[0]["subcategory"] == "r" and rows[0]["points"] == 1
    assert rows[0]["removed_by"] == "555" and rows[0]["why"] == "запись отвергнута"
    # Снимать нечего - и следа нет.
    assert db.cancel_task_on(sid, g["id"], "2026-09-28", "r") is False
    assert len(_removals(sid)) == 1


def test_lesson_removal_leaves_trail(test_db):
    sid, g = _student()
    with db.db() as c:
        c.execute("INSERT INTO score_events(student_id,group_id,date,category,subcategory,points)"
                  " VALUES(?,?,?,'attendance','online',5)", (sid, g["id"], "2026-09-27"))
    assert db.remove_lesson_attendance(sid, g["id"], "2026-09-27", by=42) is True
    rows = _removals(sid)
    assert rows[0]["points"] == 5 and rows[0]["removed_by"] == "42"
    assert rows[0]["why"] == "устаз снял отметку урока"


def test_help_for_app_only_group_does_not_promise_chat_reports():
    from core.i18n import help_student
    text = help_student(["m", "r", "t"], "pro", "ru", app_only=True)
    assert "в приложении" in text and "Пиши что выполнил" not in text
    assert "Ясир, ...?" not in help_student(["m"], "pro", "ru")
