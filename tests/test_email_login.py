"""Вход по почте (core/email_login.py, 07.10.2026)."""
import asyncio

import pytest

import core.db as db
import core.mufradat_api as api
from core import email_login as el
from core import web_auth as wa

pytestmark = pytest.mark.usefixtures("test_hadiths_db")


def _post(path, body):
    async def run():
        from aiohttp.test_utils import TestClient, TestServer
        client = TestClient(TestServer(api.build_app()))
        await client.start_server()
        try:
            resp = await client.request("POST", path, json=body)
            return resp.status, (await resp.json())
        finally:
            await client.close()
    return asyncio.run(run())


def _get(path):
    async def run():
        from aiohttp.test_utils import TestClient, TestServer
        client = TestClient(TestServer(api.build_app()))
        await client.start_server()
        try:
            resp = await client.request("GET", path)
            return resp.status, (await resp.json())
        finally:
            await client.close()
    return asyncio.run(run())


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(api, "mail_configured", lambda: True)
    monkeypatch.setattr(api, "send_mail", lambda to, subj, text, html=None: sent.append((to, text)) or True)
    monkeypatch.setattr(api, "_login_hits", {})
    return sent


def _code_from(outbox):
    import re
    return re.search(r"\b(\d{6})\b", outbox[-1][1]).group(1)


def test_normalize():
    assert el.normalize_email("  Salamat@Mail.RU ") == "salamat@mail.ru"
    assert el.normalize_email("не почта") is None
    assert el.normalize_email("") is None


def test_one_email_one_person():
    el.link_email("a@mail.ru", "111", "male")
    el.link_email("A@mail.ru", "111", "male")          # повтор - не ошибка
    with pytest.raises(ValueError, match="email_taken"):
        el.link_email("a@mail.ru", "222", "male")
    assert el.owner_of("a@mail.ru") == ("111", "male")


def test_unknown_email_is_named_honestly(test_db, outbox):
    status, d = _post("/api/muf/auth/email/start", {"email": "x@mail.ru"})
    assert status == 400 and d["error"] == "not_linked"
    assert outbox == []


def test_mail_not_configured(test_db, monkeypatch):
    monkeypatch.setattr(api, "mail_configured", lambda: False)
    status, d = _post("/api/muf/auth/email/start", {"email": "x@mail.ru"})
    assert status == 503 and d["error"] == "mail_off"


def test_full_way_to_a_session(test_db, outbox):
    """Почта -> код в письме -> код входа -> тот же /auth/poll, что и после
    Telegram -> сессия на Telegram ID человека."""
    db.save_group("-100901", "G2C", tasks="m,r,t")
    db.add_student("Саламат", db.get_group("-100901")["id"], phone="555")
    el.link_email("salamat@mail.ru", "555", "male")

    status, d = _post("/api/muf/auth/email/start", {"email": "Salamat@mail.ru"})
    assert status == 200 and d["sent"]
    assert outbox[-1][0] == "salamat@mail.ru"

    status, d = _post("/api/muf/auth/email/verify", {"email": "salamat@mail.ru", "code": _code_from(outbox)})
    assert status == 200 and d["profile"] == "male"

    status, d = _get("/api/muf/auth/poll?code=" + d["code"])
    assert wa.resolve_session(d["token"]) == "555"
    # Код из письма одноразовый
    status, d = _post("/api/muf/auth/email/verify", {"email": "salamat@mail.ru", "code": _code_from(outbox)})
    assert d["error"] == "expired"


def test_sister_gets_code_for_her_half(test_db, outbox):
    """Письмо шлёт мужской процесс, а код входа подтверждён для женского -
    сессию выдаст он, из своей базы."""
    el.link_email("s@mail.ru", "777", "female")
    _post("/api/muf/auth/email/start", {"email": "s@mail.ru"})
    status, d = _post("/api/muf/auth/email/verify", {"email": "s@mail.ru", "code": _code_from(outbox)})
    assert d["profile"] == "female"
    assert wa.take_session_for_code(d["code"]) is None      # мужской процесс сессию не выдаёт
    assert wa.login_code_profile(d["code"]) == "female"


def test_five_wrong_tries_burn_the_code(test_db, outbox):
    el.link_email("a@mail.ru", "111", "male")
    _post("/api/muf/auth/email/start", {"email": "a@mail.ru"})
    good = _code_from(outbox)
    bad = "000000" if good != "000000" else "111111"
    for _ in range(el.MAX_ATTEMPTS - 1):
        assert el.check_code("a@mail.ru", bad)[2] == "wrong"
    assert el.check_code("a@mail.ru", bad)[2] == "expired"
    assert el.check_code("a@mail.ru", good)[2] == "expired"


def test_only_last_letter_counts(test_db, outbox):
    el.link_email("a@mail.ru", "111", "male")
    _post("/api/muf/auth/email/start", {"email": "a@mail.ru"})
    first = _code_from(outbox)
    _post("/api/muf/auth/email/start", {"email": "a@mail.ru"})
    second = _code_from(outbox)
    if first != second:
        assert el.check_code("a@mail.ru", first)[2] in ("wrong", "expired")
    assert el.check_code("a@mail.ru", second)[2] is None


def test_letters_per_hour_are_capped(test_db, outbox):
    el.link_email("a@mail.ru", "111", "male")
    for _ in range(el.MAX_SENDS_PER_HOUR):
        assert _post("/api/muf/auth/email/start", {"email": "a@mail.ru"})[0] == 200
    status, d = _post("/api/muf/auth/email/start", {"email": "a@mail.ru"})
    assert status == 429 and d["error"] == "too_many"
