"""Вердикт устаза «принято / на пересдачу» и гейт пересдачи.

Решения пользователя 04.09.2026:
  - гейт включён: не пересдал — следующий этап закрыт (строка → полстраницы →
    страница → строка следующей страницы);
  - блокирует ТОЛЬКО вердикт retake. «Ещё не проверено» не блокирует, иначе
    забывчивость устаза останавливает студента насовсем;
  - извещение о вердикте идёт и в группу реплаем, и в личку;
  - голосовое замечание можно записать и при «принято».
"""

import asyncio

import core.db as db
import core.mufradat_bot as bot


CHAT = "-100444001"


def _group():
    db.save_group(CHAT, "N-1", tasks="m,r,t")
    return db.get_group(CHAT)


def _submission(sid, group, msg_id, page, line, stage):
    db.save_voice_submission(sid, group["id"], CHAT, msg_id, db.get_date(),
                             file_id="f%d" % msg_id,
                             hifz_page=page, hifz_line=line, hifz_stage=stage)
    return db.get_student_submissions(sid)[0]["id"]


def test_retake_blocks_other_units(test_db):
    group = _group()
    sid = db.add_student("Сатар", group["id"], phone="777001")
    sub_id = _submission(sid, group, 1, 6, 7, 1)

    db.set_submission_verdict(sub_id, db.VERDICT_RETAKE, "888002", [{"line": 7, "word": 2}])
    blocking = db.get_blocking_retake(sid, group["id"])

    assert blocking is not None
    assert (blocking["hifz_page"], blocking["hifz_line"]) == (6, 7)


def test_accepted_retake_unblocks(test_db):
    """Гейт снимает не любая сдача, а ПРИНЯТАЯ сдача той же единицы."""
    group = _group()
    sid = db.add_student("Сатар", group["id"], phone="777001")
    first = _submission(sid, group, 1, 6, 7, 1)
    db.set_submission_verdict(first, db.VERDICT_RETAKE, "888002")

    second = _submission(sid, group, 2, 6, 7, 1)
    db.set_submission_verdict(second, db.VERDICT_ACCEPTED, "888002")

    assert db.get_blocking_retake(sid, group["id"]) is None


def test_accepted_retake_unblocks_even_with_same_verdict_at(test_db, monkeypatch):
    """Живой баг 04.09.2026: пересдал - тут же приняли, и оба вердикта
    попали в одну и ту же миллисекунду verdict_at (грубое разрешение
    системных часов). Строгое "verdict_at > ..." тогда не находило только
    что принятую пересдачу - гейт не снимался. Замораживаем время явно,
    чтобы совпадение было не везением теста, а гарантией."""
    frozen = db.get_now()
    monkeypatch.setattr(db, "get_now", lambda: frozen)
    group = _group()
    sid = db.add_student("Сатар", group["id"], phone="777001")
    first = _submission(sid, group, 1, 6, 7, 1)
    db.set_submission_verdict(first, db.VERDICT_RETAKE, "888002")

    second = _submission(sid, group, 2, 6, 7, 1)
    db.set_submission_verdict(second, db.VERDICT_ACCEPTED, "888002")

    assert db.get_blocking_retake(sid, group["id"]) is None


def test_unchecked_submission_never_blocks(test_db):
    """Молчание устаза не должно останавливать студента."""
    group = _group()
    sid = db.add_student("Сатар", group["id"], phone="777001")
    _submission(sid, group, 1, 6, 7, 1)

    assert db.get_blocking_retake(sid, group["id"]) is None


def test_verdict_marks_submission_reviewed(test_db):
    """Вердикт и есть проверка — отдельной реакции ждать больше нечего."""
    group = _group()
    sid = db.add_student("Сатар", group["id"], phone="777001")
    sub_id = _submission(sid, group, 1, 6, 7, 1)

    db.set_submission_verdict(sub_id, db.VERDICT_ACCEPTED, "888002")

    assert db.count_pending_voice_reviews([group["id"]]) == 0
    row = db.get_student_submissions(sid)[0]
    assert row["verdict"] == "accepted"


def test_error_words_reach_the_student(test_db):
    group = _group()
    sid = db.add_student("Сатар", group["id"], phone="777001")
    sub_id = _submission(sid, group, 1, 6, 7, 1)

    db.set_submission_verdict(sub_id, db.VERDICT_RETAKE, "888002",
                              [{"line": 7, "word": 2}, {"line": 7, "word": 5}])

    assert db.get_student_submissions(sid)[0]["error_words"] == \
        '[{"line": 7, "word": 2}, {"line": 7, "word": 5}]'


def test_submit_refuses_other_unit_while_retake_pending(test_db, monkeypatch):
    """Главная проверка гейта: сдать ДРУГУЮ единицу нельзя, ту же — можно."""
    group = _group()
    db.update_group_type(CHAT, "pro")
    sid = db.add_student("Сатар", group["id"], phone="777001")
    sub_id = _submission(sid, group, 1, 6, 7, 1)
    db.set_submission_verdict(sub_id, db.VERDICT_RETAKE, "888002")

    sent = {}

    async def fake_transcode(audio):
        return b"ogg"

    async def fake_send_voice(chat_id, ogg, caption=None, reply_to_message_id=None):
        sent["voice"] = caption
        return {"ok": True, "result": {"message_id": 99, "voice": {"file_id": "x"}}}

    async def fake_send_photo(chat_id, img, name, caption=None):
        return {"ok": True, "result": {"message_id": 98}}

    async def fake_send_message(chat_id, text, reply_to_message_id=None):
        sent.setdefault("messages", []).append(text)

    monkeypatch.setattr(bot, "transcode_to_ogg", fake_transcode)
    monkeypatch.setattr(bot, "send_voice_bytes", fake_send_voice)
    monkeypatch.setattr(bot, "send_photo_bytes", fake_send_photo)
    monkeypatch.setattr(bot, "send_message", fake_send_message)

    blocked = asyncio.run(bot.submit_hifz_recording(
        "777001", b"audio", None, page=6, line=8, stage=1))
    assert blocked["ok"] is False
    assert blocked["error"] == "retake_pending"
    assert blocked["retake"] == {"page": 6, "line": 7, "stage": 1}

    same = asyncio.run(bot.submit_hifz_recording(
        "777001", b"audio", None, page=6, line=7, stage=1))
    assert same["ok"] is True


def test_verdict_notifies_group_and_dm(test_db, monkeypatch):
    group = _group()
    sid = db.add_student("Сатар", group["id"], phone="777001")
    sub_id = _submission(sid, group, 1, 6, 7, 1)
    db.mark_dm_ok(sid)
    sent = []

    async def fake_send_message(chat_id, text, reply_to_message_id=None):
        sent.append((str(chat_id), text, reply_to_message_id))

    monkeypatch.setattr(bot, "send_message", fake_send_message)

    res = asyncio.run(bot.submit_ustaz_verdict("888002", sub_id, db.VERDICT_RETAKE,
                                               [{"line": 7, "word": 2}]))

    assert res["ok"] is True
    assert sent[0][0] == CHAT and sent[0][2] == 1     # реплай на саму сдачу
    assert sent[1][0] == "777001"                     # личка студенту
    assert "пересдать" in sent[0][1]


# ── Права на проверку (эндпоинты кабинета) ────────────────────────────────

def _api_call(make_app, method, path, user_id, json_body=None):
    async def run():
        from aiohttp.test_utils import TestClient, TestServer
        client = TestClient(TestServer(make_app()))
        await client.start_server()
        try:
            resp = await client.request(method, path,
                                        headers={"X-Telegram-Init-Data": user_id},
                                        json=json_body)
            return resp.status, (await resp.json())
        finally:
            await client.close()
    return asyncio.run(run())


def test_foreign_ustaz_cannot_open_or_judge(test_db, monkeypatch):
    """Устаз чужой группы не видит сдачу и не может поставить вердикт."""
    import core.mufradat_api as api
    monkeypatch.setattr(api, "validate_init_data", lambda raw, token: {"id": raw})
    monkeypatch.setattr(api, "SUPER_ADMIN_IDS", [])
    app = api.build_app

    group = _group()
    db.save_group("-100444002", "Чужая", tasks="m,r,t")
    other = db.get_group("-100444002")
    db.add_group_admin(other["id"], "888003")
    sid = db.add_student("Сатар", group["id"], phone="777001")
    sub_id = _submission(sid, group, 1, 6, 7, 1)

    status, _ = _api_call(app, "GET", "/api/muf/ustaz/submission?id=%d" % sub_id, "888003")
    assert status == 403

    status, _ = _api_call(app, "POST", "/api/muf/ustaz/verdict", "888003",
                          {"id": sub_id, "verdict": "accepted", "words": []})
    assert status == 403
    assert db.get_student_submissions(sid)[0]["verdict"] is None


def test_own_ustaz_sees_submission_with_marks(test_db, monkeypatch):
    import core.mufradat_api as api
    monkeypatch.setattr(api, "validate_init_data", lambda raw, token: {"id": raw})
    monkeypatch.setattr(api, "SUPER_ADMIN_IDS", [])
    app = api.build_app

    group = _group()
    db.add_group_admin(group["id"], "888002")
    sid = db.add_student("Сатар", group["id"], phone="777001")
    sub_id = _submission(sid, group, 1, 6, 7, 1)
    db.set_submission_verdict(sub_id, db.VERDICT_RETAKE, "888002", [{"line": 7, "word": 2}])

    status, data = _api_call(app, "GET", "/api/muf/ustaz/submission?id=%d" % sub_id, "888002")

    assert status == 200
    assert data["student_name"] == "Сатар"
    assert data["error_words"] == [{"line": 7, "word": 2}]
    assert data["verdict"] == "retake"
