"""Кабинет студента «Сдачи»: свои записи, разбор устаза, пересдача.

Экран из макета 01.09 (screen `mine`). Вердикта «принято / на пересдачу» в
базе пока нет — есть только reviewed_at, — поэтому статуса ровно два, а
«Пересдать» доступна всегда. Вердикт отдельным заходом: он меняет контракт с
устазами (пункт 11 макета — пока не принято, следующий этап закрыт).
"""

import asyncio

import core.db as db
import core.mufradat_api as api


CHAT = "-100555001"


def _group():
    db.save_group(CHAT, "N-1", tasks="m,r,t")
    return db.get_group(CHAT)


def _call(make_app, path, user_id):
    async def run():
        from aiohttp.test_utils import TestClient, TestServer
        client = TestClient(TestServer(make_app()))
        await client.start_server()
        try:
            resp = await client.get(path, headers={"X-Telegram-Init-Data": user_id})
            data = await resp.json() if resp.content_type == "application/json" else None
            return resp.status, data
        finally:
            await client.close()
    return asyncio.run(run())


def _setup(monkeypatch):
    monkeypatch.setattr(api, "validate_init_data", lambda raw, token: {"id": raw})
    monkeypatch.setattr(api, "SUPER_ADMIN_IDS", [])
    return api.build_app


def test_submissions_carry_place_status_and_audio_flags(test_db):
    group = _group()
    sid = db.add_student("Сатар", group["id"], phone="777001")
    db.save_voice_submission(sid, group["id"], CHAT, 10, db.get_date(),
                             file_id="own-file", hifz_page=6, hifz_line=7, hifz_stage=1)

    row = db.get_student_submissions(sid)[0]

    assert (row["hifz_page"], row["hifz_line"], row["hifz_stage"]) == (6, 7, 1)
    assert row["has_audio"] == 1
    assert row["has_review_audio"] == 0
    assert row["reviewed_at"] is None
    assert row["group_title"] == "N-1"


def test_review_from_any_ustaz_reaches_the_student(test_db):
    """Раньше разбор сохранялся только от Умар устаза — студенты остальных
    групп не увидели бы в приложении ничего."""
    group = _group()
    sid = db.add_student("Сатар", group["id"], phone="777001")
    db.add_student("Устаз группы", group["id"], phone="888002")
    db.save_voice_submission(sid, group["id"], CHAT, 10, db.get_date(), file_id="own")

    db.save_submission_review(CHAT, 10, "voice", review_file_id="review-file",
                              review_by="888002")

    row = db.get_student_submissions(sid)[0]
    assert row["review_type"] == "voice"
    assert row["has_review_audio"] == 1
    assert row["review_by_name"] == "Устаз группы"


def test_review_can_be_attached_through_the_picture(test_db):
    """Устаз отвечает реплаем на картинку со строчкой — разбор всё равно
    должен привязаться к сдаче (та же дыра, что и с отметкой «проверено»)."""
    group = _group()
    sid = db.add_student("Сатар", group["id"], phone="777001")
    db.save_voice_submission(sid, group["id"], CHAT, 42, db.get_date(),
                             photo_message_id=41)

    db.save_submission_review(CHAT, 41, "text", review_text="Машаа Аллах",
                              review_by="888002")

    assert db.get_student_submissions(sid)[0]["review_text"] == "Машаа Аллах"


def test_audio_belongs_only_to_its_owner(test_db):
    """Чужую запись не отдаём даже при подобранном id сдачи."""
    group = _group()
    mine = db.add_student("Сатар", group["id"], phone="777001")
    other = db.add_student("Другой", group["id"], phone="777002")
    db.save_voice_submission(mine, group["id"], CHAT, 10, db.get_date(), file_id="own-file")
    sub_id = db.get_student_submissions(mine)[0]["id"]

    assert db.get_submission_audio(sub_id, mine, "own") == "own-file"
    assert db.get_submission_audio(sub_id, other, "own") is None


def test_api_returns_my_submissions(test_db, monkeypatch):
    app = _setup(monkeypatch)
    group = _group()
    sid = db.add_student("Сатар", group["id"], phone="777001")
    db.save_voice_submission(sid, group["id"], CHAT, 10, db.get_date(),
                             file_id="own", hifz_page=6, hifz_line=7, hifz_stage=1)

    status, data = _call(app, "/api/muf/submissions", "777001")

    assert status == 200
    assert len(data["items"]) == 1
    assert data["items"][0]["hifz_page"] == 6


def test_api_refuses_foreign_audio(test_db, monkeypatch):
    """Ответ 404 приходит ДО похода в Telegram — проверка владения в SQL."""
    app = _setup(monkeypatch)
    group = _group()
    mine = db.add_student("Сатар", group["id"], phone="777001")
    db.add_student("Другой", group["id"], phone="777002")
    db.save_voice_submission(mine, group["id"], CHAT, 10, db.get_date(), file_id="own")
    sub_id = db.get_student_submissions(mine)[0]["id"]

    status, _ = _call(app, "/api/muf/submissions/audio?id=%d&kind=own" % sub_id, "777002")

    assert status == 404
