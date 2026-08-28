import asyncio

import core.db as db
import core.mufradat_bot as mb


def _setup_group(chat_id="-100901", tasks="m,r,t"):
    db.save_group(chat_id, "Test Revision Group", tasks=tasks)
    db.update_group_type(chat_id, "pro")
    return db.get_group(chat_id)


def _capture(monkeypatch):
    sent = []

    async def fake_send_message(chat_id, text):
        sent.append((chat_id, text))

    monkeypatch.setattr(mb, "send_message", fake_send_message)
    return sent


def test_revision_credit_sends_group_message_and_saves_report(test_db, monkeypatch):
    group = _setup_group()
    uid = db.add_student("Test Student", group["id"], phone="999888777")
    sent = _capture(monkeypatch)

    credited = asyncio.run(mb.credit_revision_task("999888777"))

    assert credited is True
    assert len(sent) == 1
    assert sent[0][0] == group["chat_id"]
    assert sent[0][1] == "Test Student, повторение + (через YassirApp, Мусхаф)."

    report = db.get_today_report(uid, group["id"])
    assert report["r"] is True


def test_revision_credit_idempotent_same_day(test_db, monkeypatch):
    group = _setup_group()
    db.add_student("Test Student", group["id"], phone="999888777")
    sent = _capture(monkeypatch)

    asyncio.run(mb.credit_revision_task("999888777"))
    sent.clear()
    credited_again = asyncio.run(mb.credit_revision_task("999888777"))

    assert credited_again is False
    assert sent == []  # не спамим группу повторно


def test_revision_credit_noop_if_group_has_no_r_task(test_db, monkeypatch):
    group = _setup_group(tasks="m,t")  # без "r"
    db.add_student("Test Student", group["id"], phone="999888777")
    sent = _capture(monkeypatch)

    credited = asyncio.run(mb.credit_revision_task("999888777"))

    assert credited is False
    assert sent == []


def test_revision_credit_unknown_user_noop(test_db, monkeypatch):
    sent = _capture(monkeypatch)
    credited = asyncio.run(mb.credit_revision_task("nonexistent_uid"))
    assert credited is False
    assert sent == []
