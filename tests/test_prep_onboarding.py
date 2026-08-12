import asyncio

import core.db as db
import core.prep as prep


def _setup_prep_group():
    db.save_group("-100777", "Test Prep", tasks="m,r,t")
    db.update_group_type("-100777", "prep")
    return db.get_group("-100777")


def _capture(monkeypatch):
    sent = []

    async def fake_send_message(chat_id, text, reply_to_message_id=None):
        sent.append(("text", chat_id, text))

    async def fake_send_photo(chat_id, photo_path, caption=None):
        sent.append(("photo", chat_id, photo_path))

    monkeypatch.setattr(prep, "send_message", fake_send_message)
    monkeypatch.setattr(prep, "send_photo", fake_send_photo)
    return sent


def test_is_active_prep_student_true_for_prep(test_db):
    g = _setup_prep_group()
    db.add_student("Азим", g["id"], phone="p1")
    assert db.is_active_prep_student("p1") is True


def test_is_active_prep_student_false_for_regular_group(test_db):
    db.save_group("-100778", "Regular Group")
    g = db.get_group("-100778")
    db.add_student("Бахтияр", g["id"], phone="p2")
    assert db.is_active_prep_student("p2") is False


def test_is_active_prep_student_false_unknown_phone(test_db):
    assert db.is_active_prep_student("nobody") is False


def test_onboarding_group_message_needs_start_when_dm_not_ok(test_db, monkeypatch):
    sent = _capture(monkeypatch)

    async def fake_link():
        return "https://t.me/testbot?start=go"
    monkeypatch.setattr(prep, "get_dm_start_link", fake_link)

    asyncio.run(prep.send_prep_onboarding_group_message("-100777", "Азим", "ru", dm_ok=False))

    assert len(sent) == 1
    assert "Start" in sent[0][2]
    assert "testbot" in sent[0][2]


def test_onboarding_group_message_skips_link_when_dm_ok(test_db, monkeypatch):
    sent = _capture(monkeypatch)
    asyncio.run(prep.send_prep_onboarding_group_message("-100777", "Азим", "ru", dm_ok=True))

    assert len(sent) == 1
    assert "личные сообщения" in sent[0][2]


def test_onboarding_dm_sends_six_messages_with_three_photos(test_db, monkeypatch):
    sent = _capture(monkeypatch)
    monkeypatch.setattr(prep, "_ONBOARDING_DELAY", 0)

    asyncio.run(prep.send_prep_onboarding_dm("p1", "ru"))

    texts = [s for s in sent if s[0] == "text"]
    photos = [s for s in sent if s[0] == "photo"]
    assert len(texts) == 6
    assert len(photos) == 3
    assert {p[2].split("\\")[-1].split("/")[-1] for p in photos} == {
        "Заучивание.PNG", "Повторение.PNG", "Слова.PNG"
    }


def test_onboarding_if_pending_sends_for_active_prep_student(test_db, monkeypatch):
    g = _setup_prep_group()
    db.add_student("Азим", g["id"], phone="p1")
    sent = _capture(monkeypatch)
    monkeypatch.setattr(prep, "_ONBOARDING_DELAY", 0)

    asyncio.run(prep.send_prep_onboarding_if_pending("p1"))

    assert len([s for s in sent if s[0] == "text"]) == 6


def test_onboarding_if_pending_noop_for_non_prep_student(test_db, monkeypatch):
    db.save_group("-100779", "Regular")
    g = db.get_group("-100779")
    db.add_student("Санжар", g["id"], phone="p3")
    sent = _capture(monkeypatch)

    asyncio.run(prep.send_prep_onboarding_if_pending("p3"))

    assert sent == []
