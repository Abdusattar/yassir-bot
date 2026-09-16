"""Повторение записью для несовершеннолетних (16.09.2026).

Правило: год рождения стоит и «по году» студенту ещё не больше 18 - тап 🔁 не
засчитывается, текстовое «повторение» в группе тоже, засчитывает только
запись чтения из приложения. Год, поставленный устазом, заперт от правки.
"""
import asyncio

import core.db as db
import core.mufradat_bot as mb


PHONE = "999777666"


def _student(tasks="m,r,t"):
    db.save_group("-100903", "Test Rev Group", tasks=tasks)
    db.update_group_type("-100903", "pro")
    group = db.get_group("-100903")
    uid = db.add_student("Юный", group["id"], phone=PHONE)
    return uid, group


def test_required_until_end_of_year_they_turn_18(test_db):
    _student()
    db.set_student_birth_year(PHONE, 2008)
    assert db.revision_record_required(PHONE, today="2026-09-16") is True
    assert db.revision_record_required(PHONE, today="2027-01-01") is False
    db.set_student_birth_year(PHONE, 1990)
    assert db.revision_record_required(PHONE, today="2026-09-16") is False


def test_no_birth_year_means_adult(test_db):
    _student()
    assert db.revision_record_required(PHONE) is False


def test_locked_birth_year_cannot_be_changed_from_settings(test_db):
    _student()
    db.set_student_birth_year(PHONE, 2010)
    assert db.get_profile(PHONE)["birth_year_locked"] is True
    try:
        db.update_profile(PHONE, birth_year="2000")
    except ValueError as e:
        assert str(e) == "birth_year_locked"
    else:
        raise AssertionError("замок не сработал")
    assert db.get_profile(PHONE)["birth_year"] == 2010
    # имя править можно - замок только на годе
    db.update_profile(PHONE, name="Юный Хафиз")
    assert db.get_profile(PHONE)["name"] == "Юный Хафиз"
    # снятие года снимает и замок
    db.set_student_birth_year(PHONE, None)
    assert db.get_profile(PHONE)["birth_year_locked"] is False


def test_tap_credit_refused_for_minor(test_db, monkeypatch):
    uid, group = _student()
    db.set_student_birth_year(PHONE, 2012)
    sent = []

    async def fake_send_message(chat_id, text):
        sent.append(text)

    monkeypatch.setattr(mb, "send_message", fake_send_message)
    assert asyncio.run(mb.credit_revision_task(PHONE)) is False
    assert sent == []
    assert not (db.get_today_report(uid, group["id"]) or {}).get("r")


def _capture(monkeypatch, duration=0):
    sent = []

    async def fake_transcode(audio_bytes):
        return audio_bytes

    async def fake_send_voice(chat_id, voice_bytes, caption=None, reply_to_message_id=None):
        sent.append((chat_id, caption))
        return {"ok": True, "result": {"message_id": 500 + len(sent),
                                       "voice": {"file_id": "REV", "duration": duration}}}

    monkeypatch.setattr(mb, "transcode_to_ogg", fake_transcode)
    monkeypatch.setattr(mb, "send_voice_bytes", fake_send_voice)
    return sent


def test_recording_credits_r_and_goes_to_group_with_span(test_db, monkeypatch):
    uid, group = _student()
    db.set_student_birth_year(PHONE, 2012)
    sent = _capture(monkeypatch)
    import core.mushaf_words as mw
    monkeypatch.setattr(mb, "get_hifz_pointer", lambda u: {"page": 17, "line": 3, "stage": 1})

    res = asyncio.run(mb.submit_revision_recording(PHONE, b"AUDIO", client_ms=760_000))

    assert res["ok"] and res["credited"] and res["page_to"] == 17
    assert sent == [(group["chat_id"], "Юный, повторение + (запись 12:40, стр. 2–17).")]
    assert db.get_today_report(uid, group["id"])["r"] is True
    recs = db.get_revision_recordings([group["id"]])
    assert len(recs) == 1
    assert recs[0]["duration"] == 760 and recs[0]["page_to"] == 17 and recs[0]["short"] == 0


def test_short_recording_is_flagged_for_ustaz_but_still_credited(test_db, monkeypatch):
    uid, group = _student()
    sent = _capture(monkeypatch)
    monkeypatch.setattr(mb, "get_hifz_pointer", lambda u: {"page": 17, "line": 3, "stage": 1})

    # 16 страниц за 3 минуты - явно не читал
    res = asyncio.run(mb.submit_revision_recording(PHONE, b"AUDIO", client_ms=180_000))

    assert res["ok"]
    assert db.get_revision_recordings([group["id"]])[0]["short"] == 1
    # в группу «коротко» не уходит - без обвинительного тона
    assert "коротко" not in sent[0][1]


def test_second_recording_same_day_sent_without_plus(test_db, monkeypatch):
    uid, group = _student()
    sent = _capture(monkeypatch)
    monkeypatch.setattr(mb, "get_hifz_pointer", lambda u: None)

    asyncio.run(mb.submit_revision_recording(PHONE, b"A", client_ms=60_000, page_to=5))
    res = asyncio.run(mb.submit_revision_recording(PHONE, b"B", client_ms=60_000, page_to=5))

    assert res["credited"] is False
    assert sent[1][1] == "Юный, повторение (запись 1:00, стр. 2–5)."


def test_telegram_duration_wins_over_client_ms(test_db, monkeypatch):
    uid, group = _student()
    _capture(monkeypatch, duration=99)
    monkeypatch.setattr(mb, "get_hifz_pointer", lambda u: None)
    asyncio.run(mb.submit_revision_recording(PHONE, b"A", client_ms=60_000, page_to=3))
    assert db.get_revision_recordings([group["id"]])[0]["duration"] == 99


def test_no_r_task_in_group(test_db, monkeypatch):
    _student(tasks="m,t")
    _capture(monkeypatch)
    res = asyncio.run(mb.submit_revision_recording(PHONE, b"A", client_ms=60_000))
    assert res == {"ok": False, "error": "no_group"}


def test_text_revision_in_group_not_credited_for_minor(test_db, monkeypatch):
    """Обход через чат: «повторение» текстом в группе. Несовершеннолетнему
    не засчитывается, бот говорит, где сдавать; другие задания из того же
    сообщения засчитываются."""
    import core.handlers as h
    uid, group = _student()
    db.set_student_birth_year(PHONE, 2012)
    sent = []

    async def fake_send(chat_id, text, **kw):
        sent.append(text)

    monkeypatch.setattr(h, "send_message", fake_send)
    asyncio.run(h.process_message(chat_id=group["chat_id"], sender=PHONE,
                                  text="повторение", sender_name="Юный"))
    report = db.get_today_report(uid, group["id"]) or {}
    assert not report.get("r")
    assert any("записью" in t and "🔁" in t for t in sent), sent

    asyncio.run(h.process_message(chat_id=group["chat_id"], sender=PHONE,
                                  text="заучивание, повторение", sender_name="Юный"))
    report = db.get_today_report(uid, group["id"]) or {}
    assert report.get("m") and not report.get("r")


def test_text_revision_in_group_credited_for_adult(test_db, monkeypatch):
    import core.handlers as h
    uid, group = _student()
    monkeypatch.setattr(h, "send_message", lambda cid, text, **kw: asyncio.sleep(0))
    asyncio.run(h.process_message(chat_id=group["chat_id"], sender=PHONE,
                                  text="повторение", sender_name="Юный"))
    assert (db.get_today_report(uid, group["id"]) or {}).get("r") is True


def test_reject_removes_credit_and_notifies(test_db, monkeypatch):
    """«Отвергнуто»: балл за тот день снимается, в группу реплай на запись,
    в личку стандартное наставление."""
    import core.db as _db
    uid, group = _student()
    sent = _capture(monkeypatch)
    monkeypatch.setattr(mb, "get_hifz_pointer", lambda u: None)
    asyncio.run(mb.submit_revision_recording(PHONE, b"A", client_ms=180_000, page_to=17))
    assert db.get_today_report(uid, group["id"])["r"] is True
    rec = db.get_revision_recordings([group["id"]])[0]

    msgs = []

    async def fake_msg(chat_id, text, **kw):
        msgs.append((chat_id, text, kw.get("reply_to_message_id")))

    monkeypatch.setattr(mb, "send_message", fake_msg)
    res = asyncio.run(mb.submit_revision_verdict("ustaz1", rec["id"], "rejected"))

    assert res == {"ok": True, "verdict": "rejected"}
    assert not (db.get_today_report(uid, group["id"]) or {}).get("r")
    full = db.get_revision_recording(rec["id"])
    assert msgs[0][0] == group["chat_id"] and msgs[0][2] == full["message_id"]
    assert "не принято" in msgs[0][1]
    assert db.get_revision_recording(rec["id"])["verdict"] == "rejected"
    # у ребёнка блок «не принято» в кабинете
    assert [r["id"] for r in db.get_rejected_revisions(uid)] == [rec["id"]]


def test_new_recording_after_reject_returns_the_credit(test_db, monkeypatch):
    """Успел до полуночи — зачёт возвращает сама новая запись, и блок
    «не принято» у ребёнка гаснет."""
    uid, group = _student()
    _capture(monkeypatch)
    monkeypatch.setattr(mb, "get_hifz_pointer", lambda u: None)
    asyncio.run(mb.submit_revision_recording(PHONE, b"A", client_ms=180_000, page_to=17))
    rec = db.get_revision_recordings([group["id"]])[0]

    async def fake_msg(chat_id, text, **kw):
        return None

    monkeypatch.setattr(mb, "send_message", fake_msg)
    asyncio.run(mb.submit_revision_verdict("ustaz1", rec["id"], "rejected"))

    res = asyncio.run(mb.submit_revision_recording(PHONE, b"B", client_ms=1_500_000, page_to=17))
    assert res["credited"] is True
    assert db.get_today_report(uid, group["id"])["r"] is True
    assert db.get_rejected_revisions(uid) == []


def test_accept_returns_credit_after_mistap(test_db, monkeypatch):
    """«Принято» после ошибочного «Отвергнуто» возвращает балл."""
    uid, group = _student()
    _capture(monkeypatch)
    monkeypatch.setattr(mb, "get_hifz_pointer", lambda u: None)

    async def fake_msg(chat_id, text, **kw):
        return None

    monkeypatch.setattr(mb, "send_message", fake_msg)
    asyncio.run(mb.submit_revision_recording(PHONE, b"A", client_ms=900_000, page_to=17))
    rec = db.get_revision_recordings([group["id"]])[0]
    asyncio.run(mb.submit_revision_verdict("ustaz1", rec["id"], "rejected"))
    assert not (db.get_today_report(uid, group["id"]) or {}).get("r")

    asyncio.run(mb.submit_revision_verdict("ustaz1", rec["id"], "accepted"))
    assert db.get_today_report(uid, group["id"])["r"] is True
    assert db.get_rejected_revisions(uid) == []


def test_bad_verdict_refused(test_db, monkeypatch):
    uid, group = _student()
    _capture(monkeypatch)
    monkeypatch.setattr(mb, "get_hifz_pointer", lambda u: None)
    asyncio.run(mb.submit_revision_recording(PHONE, b"A", client_ms=60_000, page_to=3))
    rec = db.get_revision_recordings([group["id"]])[0]
    assert asyncio.run(mb.submit_revision_verdict("u", rec["id"], "maybe")) == {
        "ok": False, "error": "bad_verdict"}
