"""Все с именами (17.09.2026, правило пользователя): кто записан без имени -
бот спрашивает, не представился - перепрос, потом кик.

Запись без имени заводит mark_dm_ok_by_phone, когда человек пишет боту в
личку или входит в приложение раньше, чем в группу. Раньше такого считали
«уже известным» и регистрировали молча - в группу уходило «, Слова +»."""
import asyncio

import core.db as db
import core.handlers as h
import core.transfers as tr

CHAT = "-100905"
PHONE = "999555777"


def _prep():
    db.save_group(CHAT, "Yassir подготовительная", tasks="m,r,t")
    db.update_group_type(CHAT, "prep")
    return db.get_group(CHAT)


def _silence(monkeypatch, module=h):
    sent = []

    async def fake_send(chat_id, text, **kw):
        sent.append((chat_id, text))
    monkeypatch.setattr(module, "send_message", fake_send)
    return sent


def test_stub_from_dm_is_not_a_known_user(test_db):
    db.mark_dm_ok_by_phone(PHONE)
    assert db.find_user_by_phone(PHONE) is not None
    assert db.find_known_user_by_phone(PHONE) is None


def test_stub_writing_in_prep_is_asked_for_name(test_db, monkeypatch):
    g = _prep()
    db.mark_dm_ok_by_phone(PHONE)
    sent = _silence(monkeypatch)
    asyncio.run(h.process_message(chat_id=CHAT, sender=PHONE, text="заучивание", sender_name="Рамзан"))
    assert db.find_by_phone(PHONE, g["id"]) is None          # молча не зарегистрирован
    assert db.is_pending_name(PHONE, g["id"])
    assert any("зовут" in t or "имя" in t for _, t in sent), sent


def test_registered_without_name_is_asked_then_name_saved(test_db, monkeypatch):
    g = _prep()
    db.mark_dm_ok_by_phone(PHONE)
    uid = db.add_student("", g["id"], phone=PHONE)          # как было до исправления
    sent = _silence(monkeypatch)

    asyncio.run(h.process_message(chat_id=CHAT, sender=PHONE, text="заучивание", sender_name=""))
    assert any("не знаю твоего имени" in t for _, t in sent), sent
    assert db.get_today_report(uid, g["id"])["m"]           # сдача засчитана
    with db.db() as c:
        assert c.execute("SELECT 1 FROM unregistered_members WHERE user_id=?", (PHONE,)).fetchone()

    asyncio.run(h.process_message(chat_id=CHAT, sender=PHONE, text="Рамзан", sender_name=""))
    assert db.find_user_by_phone(PHONE)["name"] == "Рамзан"
    assert not db.is_pending_name(PHONE, g["id"])
    with db.db() as c:
        assert not c.execute("SELECT 1 FROM unregistered_members WHERE user_id=?", (PHONE,)).fetchone()


def test_nameless_student_is_asked_in_dm_and_kicked_after_days(test_db, monkeypatch):
    g = _prep()
    db.mark_dm_ok_by_phone(PHONE)
    uid = db.add_student("", g["id"], phone=PHONE)
    sent = _silence(monkeypatch, tr)
    kicked = []

    async def fake_ban(chat_id, user_id):
        kicked.append((chat_id, user_id))

    async def noop(*a, **k):
        return None
    monkeypatch.setattr("core.tg.ban_member", fake_ban)
    monkeypatch.setattr("core.tg.unban_member", noop)
    monkeypatch.setattr(tr.asyncio, "sleep", noop)

    asyncio.run(tr.kick_unregistered())                      # день 0 - вопрос в личку, не кик
    assert any(chat == PHONE and "не знаю твоего имени" in t for chat, t in sent), sent
    assert kicked == []

    with db.db() as c:
        c.execute("UPDATE unregistered_members SET joined_date=date('now','-7 days') WHERE user_id=?", (PHONE,))
    asyncio.run(tr.kick_unregistered())
    assert kicked == [(CHAT, PHONE)]
    assert db.find_by_phone(PHONE, g["id"]) is None          # членство снято
