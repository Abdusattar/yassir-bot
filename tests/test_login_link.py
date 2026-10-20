"""Ссылка для входа от супер-админа (20.10.2026, core/web_auth.py:
new_login_link / take_session_for_link, scripts/login_link.py)."""
import sqlite3
from datetime import timedelta

import pytest

import config
from core import web_auth as wa

pytestmark = pytest.mark.usefixtures("test_hadiths_db")


def test_link_logs_in_once(test_db, monkeypatch):
    monkeypatch.setattr(config, "PROFILE", "female")
    code = wa.new_login_link("8922609616", "female")
    token, uid = wa.take_session_for_link(code, "pytest")
    assert uid == "8922609616"
    assert wa.resolve_session(token) == "8922609616"
    # Пересланная дальше ссылка после первого нажатия ничего не открывает
    assert wa.take_session_for_link(code) is None


def test_other_half_link_not_spent(test_db, monkeypatch):
    """Ссылку сестры открывает мужской процесс: не тратит, а называет
    половину - вкладка переспросит женский."""
    monkeypatch.setattr(config, "PROFILE", "male")
    code = wa.new_login_link("8922609616", "female")
    assert wa.take_session_for_link(code) == ("other", "female")
    monkeypatch.setattr(config, "PROFILE", "female")
    assert wa.take_session_for_link(code)[1] == "8922609616"


def test_expired_link_refused(test_db, monkeypatch):
    monkeypatch.setattr(config, "PROFILE", "male")
    code = wa.new_login_link("1", "male", hours=24)
    later = wa.get_now() + timedelta(hours=25)
    monkeypatch.setattr(wa, "get_now", lambda: later)
    assert wa.take_session_for_link(code) is None


def test_unknown_and_empty_refused(test_db):
    assert wa.take_session_for_link("") is None
    assert wa.take_session_for_link("нет-такой") is None


def test_only_hash_stored(test_db, test_hadiths_db):
    code = wa.new_login_link("1", "male")
    with sqlite3.connect(test_hadiths_db) as c:
        stored = [r[0] for r in c.execute("SELECT code_hash FROM web_login_links")]
    assert code not in stored and len(stored) == 1


def _post_link(code):
    import asyncio
    import core.mufradat_api as api

    async def run():
        from aiohttp.test_utils import TestClient, TestServer
        client = TestClient(TestServer(api.build_app()))
        await client.start_server()
        try:
            resp = await client.post("/api/muf/auth/link", json={"code": code})
            return resp.status, (await resp.json())
        finally:
            await client.close()
    return asyncio.run(run())


def test_api_link_gives_working_token(test_db, monkeypatch):
    import core.db as db
    monkeypatch.setattr(config, "PROFILE", "male")
    db.save_group("-100901", "N-1", tasks="m,r,t")
    db.add_student("Сатар", db.get_group("-100901")["id"], phone="12345")
    code = wa.new_login_link("12345", "male")
    status, d = _post_link(code)
    assert status == 200 and d["name"] == "Сатар"
    assert wa.resolve_session(d["token"]) == "12345"
    status, d = _post_link(code)
    assert status == 400 and d["error"] == "link_bad"


def test_api_link_of_other_half_names_it(test_db, monkeypatch):
    monkeypatch.setattr(config, "PROFILE", "male")
    status, d = _post_link(wa.new_login_link("777", "female"))
    assert status == 200 and d == {"profile": "female"}
