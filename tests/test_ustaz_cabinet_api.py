"""Эндпоинт кабинета устаза: кто что видит и чей долг считает счётчик.

Правило (04.09.2026, решения пользователя по ходу сессии):
  - устаз группы видит свои группы, счётчик на двери — по своим;
  - супер-админ видит ВСЕ активные группы, счётчик — общий: он не просто
    контролирует устазов, а сам проверяет там, где устаз группы не успел
    (так делает Умар устаз), значит общий долг для него — свой долг;
  - права на приём отдельно не выдаются: is_group_admin (core/handlers.py)
    уже возвращает True супер-админу в любой группе.
"""

import asyncio
from datetime import timedelta

import core.db as db
import core.mufradat_api as api


def _call(make_app, method, path, user_id):
    """Прогон через настоящий aiohttp-стек — иначе не проверить ни декоратор
    авторизации, ни JSON-ответ целиком. Приложение строится ВНУТРИ цикла
    событий: aiohttp привязывает Application к тому циклу, в котором оно
    создано, а каждый asyncio.run() заводит свой."""
    async def run():
        from aiohttp.test_utils import TestClient, TestServer
        client = TestClient(TestServer(make_app()))
        await client.start_server()
        try:
            resp = await client.request(method, path,
                                        headers={"X-Telegram-Init-Data": user_id})
            return resp.status, (await resp.json())
        finally:
            await client.close()
    return asyncio.run(run())


def _get(make_app, path, user_id):
    return _call(make_app, "GET", path, user_id)


def _post(make_app, path, user_id):
    return _call(make_app, "POST", path, user_id)


def _setup(monkeypatch, super_ids):
    # initData не подделываем — подменяем саму проверку: её собственный
    # разбор подписи проверяется не здесь.
    monkeypatch.setattr(api, "validate_init_data", lambda raw, token: {"id": raw})
    monkeypatch.setattr(api, "SUPER_ADMIN_IDS", super_ids)
    return api.build_app


def _group(chat_id, title):
    db.save_group(chat_id, title, tasks="m,r,t")
    return db.get_group(chat_id)


def _submission(group, chat_id, msg_id, phone, days_ago=0):
    sid = db.add_student("Сатар", group["id"], phone=phone)
    date = (db.get_now() - timedelta(days=days_ago)).date().isoformat()
    db.save_voice_submission(sid, group["id"], chat_id, msg_id, date)


def test_ustaz_sees_only_his_group(test_db, monkeypatch):
    app = _setup(monkeypatch, ["999"])
    mine = _group("-100901", "N-1")
    _group("-100902", "Чужая группа")
    db.add_group_admin(mine["id"], "555")

    status, data = _get(app, "/api/muf/ustaz/waiting", "555")

    assert status == 200
    assert [g["title"] for g in data["groups"]] == ["N-1"]
    assert data["is_super"] is False


def test_super_admin_sees_every_group(test_db, monkeypatch):
    """Свои помечены mine=True и идут первыми, остальные — ниже."""
    app = _setup(monkeypatch, ["999"])
    mine = _group("-100901", "Подготовительная")
    _group("-100902", "N-2a")
    db.add_group_admin(mine["id"], "999")

    status, data = _get(app, "/api/muf/ustaz/waiting", "999")

    assert status == 200
    by_title = {g["title"]: g for g in data["groups"]}
    assert by_title["Подготовительная"]["mine"] is True
    assert by_title["N-2a"]["mine"] is False
    assert data["is_super"] is True


def test_super_admin_keeps_cabinet_without_any_ustaz_role(test_db, monkeypatch):
    """Сняв с себя роль устаза, супер-админ не должен терять кабинет —
    иначе ни контролировать устазов, ни подхватывать за ними нечем."""
    app = _setup(monkeypatch, ["999"])
    _group("-100901", "N-1")

    status, data = _get(app, "/api/muf/ustaz/waiting", "999")

    assert status == 200
    assert [g["mine"] for g in data["groups"]] == [False]


def test_plain_student_gets_no_cabinet(test_db, monkeypatch):
    app = _setup(monkeypatch, ["999"])
    _group("-100901", "N-1")

    status, _ = _get(app, "/api/muf/ustaz/waiting", "555")

    assert status == 403


def test_group_counts_split_window_and_tail(test_db, monkeypatch):
    """У каждой группы своё число ждущих — это оно светится красным."""
    app = _setup(monkeypatch, ["999"])
    grp = _group("-100901", "N-1")
    db.add_group_admin(grp["id"], "555")
    _submission(grp, "-100901", 1, "777001", days_ago=0)
    _submission(grp, "-100901", 2, "777001", days_ago=30)

    _, data = _get(app, "/api/muf/ustaz/waiting", "555")

    assert data["groups"][0]["waiting"] == 1
    assert data["groups"][0]["older"] == 1
    assert data["older"] == 1
    assert len(data["items"]) == 1


def test_door_counter_scope(test_db, monkeypatch):
    """Счётчик на двери: у устаза группы — по своим, у супер-админа — по всем."""
    app = _setup(monkeypatch, ["999"])
    mine = _group("-100901", "N-1")
    other = _group("-100902", "N-2a")
    db.add_group_admin(mine["id"], "555")
    _submission(mine, "-100901", 1, "777001")
    _submission(other, "-100902", 2, "777002")

    _, ustaz = _post(app, "/api/muf/heartbeat", "555")
    _, sup = _post(app, "/api/muf/heartbeat", "999")

    assert ustaz["is_ustaz"] is True and ustaz["waiting_count"] == 1
    assert sup["is_ustaz"] is True and sup["waiting_count"] == 2
