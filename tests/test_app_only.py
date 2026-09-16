"""Перевод групп на сдачу только через YassirApp (16.09.2026).

Решение пользователя: волнами по три группы, два дня отсчёта утром и вечером,
на третий день рубильник. После рубильника задания и отметка урока в чате не
засчитываются, узр по-прежнему работает.
"""
import asyncio

import core.db as db
import core.handlers as h


CHAT = "-100904"
PHONE = "999555444"


def _group(tasks="m,r,t"):
    db.save_group(CHAT, "Test AppOnly", tasks=tasks)
    db.update_group_type(CHAT, "relaxed")
    return db.get_group(CHAT)


def _silence(monkeypatch):
    sent = []

    async def fake_send(chat_id, text, **kw):
        sent.append(text)

    monkeypatch.setattr(h, "send_message", fake_send)
    return sent


def test_flag_switches_on_the_date(test_db):
    g = _group()
    assert db.group_app_only_active(g) is False
    db.set_group_app_only(g["id"], "2026-09-18")
    g = db.get_group(CHAT)
    assert db.group_app_only_active(g, today="2026-09-17") is False
    assert db.group_app_only_active(g, today="2026-09-18") is True
    assert db.group_app_only_active(g, today="2026-09-30") is True
    db.set_group_app_only(g["id"], None)
    assert db.group_app_only_active(db.get_group(CHAT)) is False


def test_text_report_not_credited_after_switch(test_db, monkeypatch):
    g = _group()
    uid = db.add_student("Ахмад", g["id"], phone=PHONE)
    db.set_group_app_only(g["id"], db.get_date())
    sent = _silence(monkeypatch)

    asyncio.run(h.process_message(chat_id=CHAT, sender=PHONE,
                                  text="заучивание, повторение, слова", sender_name="Ахмад"))

    assert not (db.get_today_report(uid, g["id"]) or {})
    assert any("только через YassirApp" in t for t in sent), sent


def test_text_report_still_works_before_the_date(test_db, monkeypatch):
    g = _group()
    uid = db.add_student("Ахмад", g["id"], phone=PHONE)
    db.set_group_app_only(g["id"], "2099-01-01")
    _silence(monkeypatch)

    asyncio.run(h.process_message(chat_id=CHAT, sender=PHONE,
                                  text="заучивание, повторение, слова", sender_name="Ахмад"))

    report = db.get_today_report(uid, g["id"]) or {}
    assert report.get("m") and report.get("r") and report.get("t")


def test_lesson_mark_by_text_refused_after_switch(test_db, monkeypatch):
    g = _group()
    uid = db.add_student("Ахмад", g["id"], phone=PHONE)
    db.set_group_app_only(g["id"], db.get_date())
    sent = _silence(monkeypatch)

    asyncio.run(h.process_message(chat_id=CHAT, sender=PHONE, text="у", sender_name="Ахмад"))

    assert any("Я был" in t for t in sent), sent
    with db.db() as c:
        marks = c.execute(
            "SELECT COUNT(*) FROM score_events WHERE student_id=? AND category='attendance'",
            (uid,)).fetchone()[0]
    assert marks == 0


def test_voice_in_group_not_taken_as_submission(test_db, monkeypatch):
    g = _group()
    uid = db.add_student("Ахмад", g["id"], phone=PHONE)
    db.set_group_app_only(g["id"], db.get_date())
    sent = _silence(monkeypatch)

    # bot.py помечает голосовое is_media=True (иначе пустой текст отсекается раньше)
    asyncio.run(h.process_message(chat_id=CHAT, sender=PHONE, text="", sender_name="Ахмад",
                                  is_media=True, is_voice=True, message_id=4242,
                                  voice_file_id="F", voice_duration=300))

    with db.db() as c:
        subs = c.execute("SELECT COUNT(*) FROM voice_submissions WHERE student_id=?",
                         (uid,)).fetchone()[0]
    assert subs == 0
    assert any("только через YassirApp" in t for t in sent), sent


def test_excuse_still_accepted_after_switch(test_db, monkeypatch):
    """Узр - не задание: человек объясняет, почему не сдал. Его рубильник
    не трогает, иначе бот молчит в ответ на живое сообщение."""
    g = _group()
    uid = db.add_student("Ахмад", g["id"], phone=PHONE)
    db.set_group_app_only(g["id"], db.get_date())
    sent = _silence(monkeypatch)

    asyncio.run(h.process_message(chat_id=CHAT, sender=PHONE,
                                  text="узр, сегодня болею", sender_name="Ахмад"))

    with db.db() as c:
        excuses = c.execute(
            "SELECT COUNT(*) FROM score_events WHERE student_id=? AND category='excuse'",
            (uid,)).fetchone()[0]
    assert excuses == 1, sent
