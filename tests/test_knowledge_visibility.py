"""«Знания» только по заданиям группы (14.09.2026): урок по прямому номеру не
отдаётся группе без этого предмета, подпись двери и блок «Уроки» знают, какие
предметы есть у человека."""

import asyncio

import core.db as db
import core.mufradat_api as api


def _group(chat_id, tasks):
    db.save_group(chat_id, "G", tasks=tasks)
    db.update_group_type(chat_id, "relaxed")
    return db.get_group(chat_id)


def _part(subject):
    with db.db() as c:
        cur = c.execute(
            "INSERT INTO curriculum_parts(subject, chapter, topic, part_number, part_total,"
            " order_index, content, published_at) VALUES(?,'Глава','Тема',1,1,1,'Текст',datetime('now'))",
            (subject,))
        return cur.lastrowid


def _call(path, user_id):
    # Уроки в тестах кладутся в базу уже «опубликованными» - открываем их
    # группам с этим предметом, как это сделал бы разовый перенос.
    from core import curriculum
    curriculum.backfill()

    async def run():
        from aiohttp.test_utils import TestClient, TestServer
        client = TestClient(TestServer(api.build_app()))
        await client.start_server()
        try:
            resp = await client.get(path, headers={"X-Telegram-Init-Data": user_id})
            return resp.status
        finally:
            await client.close()
    return asyncio.run(run())


def test_lesson_by_number_only_for_groups_with_the_subject(test_db, monkeypatch):
    monkeypatch.setattr(api, "validate_init_data", lambda raw, token: {"id": raw})
    monkeypatch.setattr(api, "SUPER_ADMIN_IDS", [])
    plain = _group("-100911", "m,r,t")
    with_j = _group("-100912", "m,r,t,j")
    db.add_student("Юсуф", plain["id"], phone="701")
    db.add_student("Абдулла", with_j["id"], phone="702")
    db.add_group_admin(plain["id"], "555")
    j_id, n_id = _part("j"), _part("n")

    assert _call("/api/muf/lesson?id=%d" % j_id, "701") == 404
    assert _call("/api/muf/lesson?id=%d" % j_id, "702") == 200
    assert _call("/api/muf/lesson?id=%d" % n_id, "702") == 404
    assert _call("/api/muf/lesson?id=%d" % n_id, "555") == 200      # устаз видит всё

    assert api._dashboard_facts("701")["learn"] == []
    assert api._dashboard_facts("702")["learn"] == ["j"]
    assert api._dashboard_facts("555")["learn"] == ["j", "n"]
