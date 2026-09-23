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


def test_written_nahw_and_hadith_still_accepted_after_switch(test_db, monkeypatch):
    """17.09.2026: у нахва и хадиса в приложении тренажёра ещё нет - в группе
    после рубильника они засчитываются письменно, остальное из того же
    сообщения - нет."""
    g = _group(tasks="m,r,t,j,n,h")
    uid = db.add_student("Ахмад", g["id"], phone=PHONE)
    db.set_group_app_only(g["id"], db.get_date())
    sent = _silence(monkeypatch)

    asyncio.run(h.process_message(chat_id=CHAT, sender=PHONE,
                                  text="заучивание, слова, нахв, хадис", sender_name="Ахмад"))

    report = db.get_today_report(uid, g["id"])
    assert report and report["n"] and report["h"], sent
    assert not report["m"] and not report["t"]
    assert not any("только через YassirApp" in t for t in sent), sent


def test_group_without_nahw_still_refused(test_db, monkeypatch):
    g = _group()
    uid = db.add_student("Ахмад", g["id"], phone=PHONE)
    db.set_group_app_only(g["id"], db.get_date())
    sent = _silence(monkeypatch)

    asyncio.run(h.process_message(chat_id=CHAT, sender=PHONE,
                                  text="слова, нахв", sender_name="Ахмад"))

    assert db.get_today_report(uid, g["id"]) is None
    assert any("только через YassirApp" in t for t in sent), sent


def test_countdown_tells_nahw_groups_about_written_exception(test_db, monkeypatch):
    import core.scheduler as sch
    g = _group(tasks="m,r,t,j,n")
    db.set_group_app_only(g["id"], db.get_date())
    sent = []

    async def fake_send(chat_id, text, **kw):
        sent.append(text)

    monkeypatch.setattr(sch, "send_message", fake_send)
    asyncio.run(sch.app_only_countdown())
    assert sent and "Нахв пока сдавайте в группе письменно" in sent[0], sent


# ── Письменная сдача закрыта по группе с даты (23.09.2026, нахв в N-1) ──────

def test_written_closed_by_group_and_date(test_db):
    import core.db as db
    assert db.written_closed(5, "n", "2026-09-24") is False
    db.set_setting("written_off:5:n", "2026-09-24")
    assert db.written_closed(5, "n", "2026-09-23") is False
    assert db.written_closed(5, "n", "2026-09-24") is True
    assert db.written_closed(5, "h", "2026-09-24") is False
