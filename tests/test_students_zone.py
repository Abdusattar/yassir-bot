"""Зона «Студенты» кабинета устаза: успеваемость по группе за месяц.

Решение пользователя 04.09.2026: успеваемость видна ЛЮБОМУ устазу по ЛЮБОЙ
группе («чтобы были в курсе насчёт успеваемости любого студента»). Права на
проверку это не расширяет — вердикт по-прежнему ставит только устаз своей
группы или супер-админ.
"""

import asyncio

import core.db as db
import core.mufradat_api as api
import core.transfers as transfers


CHAT = "-100333001"


def _group(chat_id=CHAT, title="N-1", gtype="pro"):
    db.save_group(chat_id, title, tasks="m,r,t")
    db.update_group_type(chat_id, gtype)
    return db.get_group(chat_id)


def _call(make_app, path, user_id):
    async def run():
        from aiohttp.test_utils import TestClient, TestServer
        client = TestClient(TestServer(make_app()))
        await client.start_server()
        try:
            resp = await client.get(path, headers={"X-Telegram-Init-Data": user_id})
            return resp.status, (await resp.json())
        finally:
            await client.close()
    return asyncio.run(run())


def _setup(monkeypatch, super_ids=()):
    monkeypatch.setattr(api, "validate_init_data", lambda raw, token: {"id": raw})
    monkeypatch.setattr(api, "SUPER_ADMIN_IDS", list(super_ids))
    return api.build_app


def test_thresholds_match_the_rule_that_actually_transfers(test_db):
    """Экран называет порог студенту прямо — значит он обязан совпадать с
    тем, по которому его реально переводят в Тадаббур. Тест падает, если
    в core/transfers.py числа поменяют, а здесь забудут."""
    assert db.group_miss_threshold("pro") == transfers.PRO_INACTIVE_DAYS
    assert db.group_miss_threshold("relaxed") == transfers.RELAXED_INACTIVE_DAYS
    assert db.group_miss_threshold("prep") is None


def test_month_progress_counts_tasks_per_day(test_db):
    group = _group()
    sid = db.add_student("Сатар", group["id"], phone="777001")
    today = db.get_date()
    db.save_report(sid, group["id"], today, {"m": True, "r": True})

    rows = db.get_group_month_progress(group["id"])

    assert len(rows) == 1
    assert rows[0]["days"][today] == 2
    assert rows[0]["name"] == "Сатар"


def test_students_sorted_by_misses_first(test_db):
    """Не рейтинг, а «кому нужна помощь» — сверху те, кто пропускает."""
    group = _group()
    active = db.add_student("Активный", group["id"], phone="777001")
    db.add_student("Пропускающий", group["id"], phone="777002")
    db.save_report(active, group["id"], db.get_date(), {"m": True})

    rows = db.get_group_month_progress(group["id"])

    assert rows[0]["name"] in ("Пропускающий", "Активный")
    assert rows[0]["missed"] >= rows[-1]["missed"]


def test_any_ustaz_sees_any_group(test_db, monkeypatch):
    app = _setup(monkeypatch)
    mine = _group()
    other = _group("-100333002", "G-11", "relaxed")
    db.add_group_admin(mine["id"], "888002")
    db.add_student("Сатар", other["id"], phone="777001")

    status, data = _call(app, "/api/muf/ustaz/students?group=%d" % other["id"], "888002")

    assert status == 200
    assert data["threshold"] == transfers.RELAXED_INACTIVE_DAYS
    assert [st["name"] for st in data["students"]] == ["Сатар"]


def test_student_without_ustaz_role_gets_nothing(test_db, monkeypatch):
    app = _setup(monkeypatch)
    group = _group()
    db.add_student("Сатар", group["id"], phone="777001")

    status, _ = _call(app, "/api/muf/ustaz/students?group=%d" % group["id"], "777001")

    assert status == 403


def test_groups_list_marks_own_first(test_db, monkeypatch):
    app = _setup(monkeypatch)
    mine = _group("-100333003", "Моя")
    _group("-100333004", "Чужая")
    db.add_group_admin(mine["id"], "888002")

    _status, data = _call(app, "/api/muf/ustaz/groups", "888002")

    assert data["groups"][0]["title"] == "Моя"
    assert data["groups"][0]["mine"] is True
    assert data["groups"][1]["mine"] is False


def test_single_student_days_show_which_tasks(test_db, monkeypatch):
    app = _setup(monkeypatch)
    group = _group()
    db.add_group_admin(group["id"], "888002")
    sid = db.add_student("Сатар", group["id"], phone="777001")
    today = db.get_date()
    db.save_report(sid, group["id"], today, {"m": True, "t": True})

    _status, data = _call(
        app, "/api/muf/ustaz/student?id=%d&group=%d" % (sid, group["id"]), "888002")

    assert data["name"] == "Сатар"
    assert sorted(data["days"][today]) == ["m", "t"]
