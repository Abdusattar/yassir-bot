"""Отметка онлайн-урока (14.09.2026): до двух отметок за календарную неделю,
сутки между ними; кнопка в приложении и «у» в Telegram - одно правило;
устаз снимает ошибочную отметку только в своей группе; «Знания» показывают
предметы по заданиям группы."""

import asyncio

import core.db as db
import core.mufradat_api as api
import core.tg as tg


def _group(chat_id="-100901", title="N-1", tasks="m,r,t"):
    db.save_group(chat_id, title, tasks=tasks)
    db.update_group_type(chat_id, "relaxed")
    return db.get_group(chat_id)


def _today(monkeypatch, day):
    monkeypatch.setattr(db, "get_date", lambda: day)


def _age_marks(hours):
    """Сдвинуть время записи отметок в прошлое - вместо ожидания суток."""
    with db.db() as c:
        c.execute("UPDATE score_events SET created_at=datetime('now', ?)"
                  " WHERE category='attendance'", ("-%d hours" % hours,))


def _call(method, path, user_id, body=None):
    async def run():
        from aiohttp.test_utils import TestClient, TestServer
        client = TestClient(TestServer(api.build_app()))
        await client.start_server()
        try:
            resp = await client.request(method, path, json=body,
                                        headers={"X-Telegram-Init-Data": user_id})
            return resp.status, (await resp.json())
        finally:
            await client.close()
    return asyncio.run(run())


def _auth(monkeypatch, supers=()):
    monkeypatch.setattr(api, "validate_init_data", lambda raw, token: {"id": raw})
    monkeypatch.setattr(api, "SUPER_ADMIN_IDS", list(supers))


def test_monday_for_last_week_and_sunday_lesson_both_count(test_db, monkeypatch):
    """Живой случай 2 группы Асмы: урок прошлой недели отмечен в понедельник,
    конференция в воскресенье той же календарной недели."""
    g = _group()
    sid = db.add_student("Бегайым", g["id"], phone="777")
    _today(monkeypatch, "2026-09-07")
    assert db.credit_lesson_attendance(sid, g["id"]) is True
    _age_marks(24 * 6)
    _today(monkeypatch, "2026-09-13")
    assert db.credit_lesson_attendance(sid, g["id"]) is True


def test_third_mark_in_a_week_is_refused(test_db, monkeypatch):
    g = _group()
    sid = db.add_student("Зубейда", g["id"], phone="777")
    for day in ("2026-09-08", "2026-09-10"):
        _today(monkeypatch, day)
        assert db.credit_lesson_attendance(sid, g["id"]) is True
        _age_marks(48)
    _today(monkeypatch, "2026-09-12")
    assert db.credit_lesson_attendance(sid, g["id"]) is False
    _today(monkeypatch, "2026-09-14")          # новая неделя
    assert db.credit_lesson_attendance(sid, g["id"]) is True


def test_repeat_after_midnight_for_the_same_lesson_is_refused(test_db, monkeypatch):
    """Сумая 13.09: вечером отказ, после полуночи повтор засчитался 14.09."""
    g = _group()
    sid = db.add_student("Сумая", g["id"], phone="777")
    _today(monkeypatch, "2026-09-13")
    assert db.credit_lesson_attendance(sid, g["id"]) is True
    assert db.lesson_attendance_status(sid, g["id"])["marked_today"] is True
    _today(monkeypatch, "2026-09-14")
    assert db.credit_lesson_attendance(sid, g["id"]) is False
    status = db.lesson_attendance_status(sid, g["id"])
    assert status["can_mark"] is False and status["week_count"] == 0


def test_move_and_remove_mark(test_db, monkeypatch):
    g = _group()
    sid = db.add_student("Мединка", g["id"], phone="777")
    _today(monkeypatch, "2026-09-14")
    db.credit_lesson_attendance(sid, g["id"])
    assert db.move_lesson_attendance(sid, g["id"], "2026-09-14", "2026-09-13") is True
    assert db.get_lesson_dates(sid, g["id"], "2026-09") == ["2026-09-13"]
    assert db.move_lesson_attendance(sid, g["id"], "2026-09-14", "2026-09-13") is False
    assert db.remove_lesson_attendance(sid, g["id"], "2026-09-13") is True
    assert db.get_lesson_dates(sid, g["id"], "2026-09") == []


def test_group_progress_carries_lesson_days(test_db, monkeypatch):
    g = _group()
    sid = db.add_student("Амина", g["id"], phone="777")
    _today(monkeypatch, "2026-09-13")
    db.credit_lesson_attendance(sid, g["id"])
    rows = db.get_group_month_progress(g["id"], "2026-09")
    assert [r["lesson_days"] for r in rows if r["id"] == sid] == [["2026-09-13"]]


def test_app_button_credits_once_and_tells_the_group(test_db, monkeypatch):
    _auth(monkeypatch)
    sent = []

    async def fake_send(chat_id, text, *a, **k):
        sent.append((chat_id, text))
        return {"ok": True}
    monkeypatch.setattr(tg, "send_message", fake_send)
    g = _group()
    db.add_student("Сатар", g["id"], phone="777")

    status, data = _call("POST", "/api/muf/lesson/mark", "777")
    assert status == 200 and data["credited"] is True
    assert data["lesson"]["marked_today"] is True and len(data["lessons"]) == 1
    assert len(sent) == 1 and "через YassirApp" in sent[0][1]

    status, data = _call("POST", "/api/muf/lesson/mark", "777")
    assert data["credited"] is False and len(sent) == 1

    status, data = _call("GET", "/api/muf/month", "777")
    assert data["lesson"]["can_mark"] is False and len(data["lessons"]) == 1


def test_ustaz_removes_only_in_his_group(test_db, monkeypatch):
    _auth(monkeypatch, ["999"])
    mine = _group("-100901", "N-1")
    other = _group("-100902", "N-2a")
    db.add_group_admin(mine["id"], "555")
    s1 = db.add_student("Абдулла", mine["id"], phone="701")
    s2 = db.add_student("Хамза", other["id"], phone="702")
    db.credit_lesson_attendance(s1, mine["id"])
    db.credit_lesson_attendance(s2, other["id"])
    today = db.get_date()

    status, _ = _call("POST", "/api/muf/ustaz/lesson/remove", "555",
                      {"student_id": s2, "group_id": other["id"], "date": today})
    assert status == 403
    status, data = _call("POST", "/api/muf/ustaz/lesson/remove", "555",
                         {"student_id": s1, "group_id": mine["id"], "date": today})
    assert status == 200 and data["ok"] is True and data["lessons"] == []

    status, data = _call("GET", "/api/muf/ustaz/student?id=%d&group=%d" % (s2, other["id"]), "555")
    assert data["can_edit_lessons"] is False


def _part(subject):
    with db.db() as c:
        c.execute(
            "INSERT INTO curriculum_parts(subject, chapter, topic, part_number, part_total,"
            " order_index, content, published_at) VALUES(?,?,?,?,?,?,?,datetime('now'))",
            (subject, "Глава", "Тема", 1, 1, 1, "Текст"))


def test_knowledge_shows_only_subjects_of_the_group(test_db, monkeypatch):
    _auth(monkeypatch)
    g = _group(tasks="m,r,t,j")
    db.add_student("Сатар", g["id"], phone="777")
    db.add_group_admin(g["id"], "555")
    _part("j")
    _part("n")

    _, data = _call("GET", "/api/muf/lessons", "777")
    assert [s["id"] for s in data["subjects"]] == ["j"]
    _, data = _call("GET", "/api/muf/lessons?subject=n", "777")
    assert data["items"] == []
    _, data = _call("GET", "/api/muf/lessons", "555")
    assert [s["id"] for s in data["subjects"]] == ["j", "n"]
