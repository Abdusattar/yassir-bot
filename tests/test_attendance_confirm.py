import asyncio

import core.db as db
import core.attendance_confirm as ac


def _setup_group_and_students(students=1):
    db.save_group("-100111", "Test Group")
    group = db.get_group("-100111")
    db.add_group_admin(group["id"], "111")
    ids = []
    for i in range(students):
        db.add_student("Student %s" % i, group["id"], phone="s%s" % i)
        s = db.find_by_phone("s%s" % i, group["id"])
        ids.append(s["id"])
    return group, ids


def _capture(monkeypatch):
    sent = []

    async def fake_send_message(chat_id, text, reply_to_message_id=None):
        sent.append((chat_id, text))

    async def fake_send_buttons(chat_id, text, buttons):
        sent.append((chat_id, text))

    monkeypatch.setattr(ac, "send_message", fake_send_message)
    monkeypatch.setattr(ac, "send_message_with_buttons", fake_send_buttons)
    return sent


def test_escalation_posts_to_group_not_admin(test_db, monkeypatch):
    group, [sid] = _setup_group_and_students()
    sent = _capture(monkeypatch)

    confirm_id, is_new = db.get_or_create_attendance_confirm(group["id"], db.get_date())
    assert is_new
    db.add_attendance_confirm_student(confirm_id, sid)

    with db.db() as c:
        c.execute("UPDATE attendance_confirm SET asked_at=datetime('now','-31 minutes') WHERE id=?", (confirm_id,))

    asyncio.run(ac.check_attendance_confirm_escalations())

    assert len(sent) == 1
    assert sent[0][0] == group["chat_id"]
    assert "напомните" in sent[0][1].lower()

    row = db.get_attendance_confirm_by_id(confirm_id)
    assert row["escalated_at"] is not None
    assert row["decision"] is None


def test_auto_resolve_denies_points_and_posts_neutral_text(test_db, monkeypatch):
    group, [sid] = _setup_group_and_students()
    sent = _capture(monkeypatch)

    confirm_id, _ = db.get_or_create_attendance_confirm(group["id"], db.get_date())
    db.add_attendance_confirm_student(confirm_id, sid)
    db.mark_attendance_confirm_escalated(confirm_id)
    with db.db() as c:
        c.execute("UPDATE attendance_confirm SET escalated_at=datetime('now','-25 hours') WHERE id=?", (confirm_id,))

    asyncio.run(ac.check_attendance_confirm_auto_resolve())

    row = db.get_attendance_confirm_by_id(confirm_id)
    assert row["decision"] == "no"
    assert row["decision_reason"] == "auto"

    with db.db() as c:
        pts = c.execute(
            "SELECT COALESCE(SUM(points),0) as p FROM score_events WHERE student_id=? AND category='attendance'",
            (sid,)
        ).fetchone()["p"]
    assert pts == 0

    assert len(sent) == 1
    text = sent[0][1].lower()
    assert "недопустимо" not in text
    assert "не успел подтвердить" in text


def test_manual_no_uses_different_text_than_auto(test_db, monkeypatch):
    group, [sid] = _setup_group_and_students()
    sent = _capture(monkeypatch)

    confirm_id, _ = db.get_or_create_attendance_confirm(group["id"], db.get_date())
    db.add_attendance_confirm_student(confirm_id, sid)

    asyncio.run(ac.resolve_attendance_confirm(confirm_id, "no", reason="manual"))

    row = db.get_attendance_confirm_by_id(confirm_id)
    assert row["decision"] == "no"
    assert row["decision_reason"] == "manual"
    assert "не успел подтвердить" not in sent[0][1].lower()


def test_yes_still_awards_points(test_db, monkeypatch):
    group, [sid] = _setup_group_and_students()
    sent = _capture(monkeypatch)

    confirm_id, _ = db.get_or_create_attendance_confirm(group["id"], db.get_date())
    db.add_attendance_confirm_student(confirm_id, sid)

    asyncio.run(ac.resolve_attendance_confirm(confirm_id, "yes", reason="manual"))

    with db.db() as c:
        pts = c.execute(
            "SELECT COALESCE(SUM(points),0) as p FROM score_events WHERE student_id=? AND category='attendance'",
            (sid,)
        ).fetchone()["p"]
    assert pts == 5
