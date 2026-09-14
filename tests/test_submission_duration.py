"""Длина записи у сдачи (14.09.2026): хранится в секундах, отдаётся кабинету
устаза, а мусор вместо числа не роняет запись."""

import asyncio

import core.db as db
import core.mufradat_api as api


def _group(chat_id, title):
    db.save_group(chat_id, title, tasks="m,r,t")
    return db.get_group(chat_id)


def _get(make_app, path, user_id):
    async def run():
        from aiohttp.test_utils import TestClient, TestServer
        client = TestClient(TestServer(make_app()))
        await client.start_server()
        try:
            resp = await client.request("GET", path, headers={"X-Telegram-Init-Data": user_id})
            return resp.status, (await resp.json())
        finally:
            await client.close()
    return asyncio.run(run())


def test_duration_is_stored_as_whole_seconds(test_db):
    g = _group("-100901", "N-1")
    sid = db.add_student("Сатар", g["id"], phone="777")
    db.save_voice_submission(sid, g["id"], "-100901", 10, db.get_date(), "f1",
                             hifz_page=6, hifz_line=0, hifz_stage=1, duration=108)
    db.save_voice_submission(sid, g["id"], "-100901", 11, db.get_date(), "f2",
                             hifz_page=6, hifz_line=1, hifz_stage=1, duration="61.7")
    db.save_voice_submission(sid, g["id"], "-100901", 12, db.get_date(), "f3",
                             hifz_page=6, hifz_line=2, hifz_stage=1, duration="мусор")
    db.save_voice_submission(sid, g["id"], "-100901", 13, db.get_date(), "f4")

    with db.db() as c:
        by_msg = {r["message_id"]: r["duration"] for r in
                  c.execute("SELECT message_id, duration FROM voice_submissions")}
    assert by_msg == {10: 108, 11: 62, 12: None, 13: None}


def test_waiting_queue_carries_duration(test_db, monkeypatch):
    monkeypatch.setattr(api, "validate_init_data", lambda raw, token: {"id": raw})
    monkeypatch.setattr(api, "SUPER_ADMIN_IDS", ["999"])
    g = _group("-100901", "N-1")
    db.add_group_admin(g["id"], "555")
    sid = db.add_student("Сатар", g["id"], phone="777")
    db.save_voice_submission(sid, g["id"], "-100901", 10, db.get_date(), "f1",
                             hifz_page=6, hifz_line=0, hifz_stage=1, duration=108)

    status, data = _get(api.build_app, "/api/muf/ustaz/waiting", "555")

    assert status == 200
    assert [it["duration"] for it in data["items"]] == [108]


def test_reviewed_list_and_backfill_candidates(test_db):
    g = _group("-100901", "N-1")
    sid = db.add_student("Сатар", g["id"], phone="777")
    db.save_voice_submission(sid, g["id"], "-100901", 10, db.get_date(), "f1",
                             hifz_page=6, hifz_line=0, hifz_stage=1)
    db.save_voice_submission(sid, g["id"], "-100901", 11, db.get_date(), "f2",
                             hifz_page=6, hifz_line=1, hifz_stage=1)
    db.mark_voice_reviewed("-100901", 11)

    # Кандидаты на добивание: по умолчанию только ждущие проверки.
    assert [r["message_id"] for r in db.get_submissions_without_duration()] == [10]
    assert [r["message_id"] for r in db.get_submissions_without_duration(pending_only=False)] == [10, 11]

    reviewed_id = db.get_submissions_without_duration(pending_only=False)[1]["id"]
    db.set_submission_duration(reviewed_id, 95.4)
    assert db.get_reviewed_submissions([g["id"]])[0]["duration"] == 95
    assert [r["message_id"] for r in db.get_submissions_without_duration(pending_only=False)] == [10]
