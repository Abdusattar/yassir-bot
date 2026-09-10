"""Вход с сайта через HTTP (core/mufradat_api.py, 10.09.2026).

Здесь проверяется то, что не видно в core/web_auth.py: что декоратор
авторизации действительно пускает по токену сессии, что без него не пускает,
и что три эндпоинта входа складываются в рабочую последовательность
«код → подтверждение ботом → токен».
"""
import asyncio

import core.mufradat_api as api
from core import web_auth as wa


def _request(method, path, headers=None):
    """Настоящий aiohttp-стек: иначе не проверить сам декоратор.
    Приложение строится ВНУТРИ цикла событий - aiohttp привязывает
    Application к тому циклу, в котором оно создано."""
    async def run():
        from aiohttp.test_utils import TestClient, TestServer
        client = TestClient(TestServer(api.build_app()))
        await client.start_server()
        try:
            resp = await client.request(method, path, headers=headers or {})
            return resp.status, (await resp.json())
        finally:
            await client.close()
    return asyncio.run(run())


def _bearer(token):
    return {"Authorization": "Bearer " + token}


def _fresh_token(user_id="12345"):
    code = wa.new_login_code()
    wa.claim_login_code(code, user_id)
    return wa.take_session_for_code(code)[0]


def test_no_credentials_at_all_is_401(test_db):
    status, _ = _request("GET", "/api/muf/state")
    assert status == 401


def test_garbage_bearer_is_401(test_db):
    status, _ = _request("GET", "/api/muf/state", _bearer("не-настоящий-токен"))
    assert status == 401


def test_session_token_opens_the_same_doors_as_telegram(test_db, test_hadiths_db):
    """Главное обещание всей затеи: снаружи Telegram приложение работает
    ровно так же, просто удостоверяется другим способом."""
    status, _ = _request("GET", "/api/muf/state", _bearer(_fresh_token()))
    assert status == 200


def test_revoked_session_is_shut_out(test_db, test_hadiths_db):
    token = _fresh_token()
    assert _request("GET", "/api/muf/state", _bearer(token))[0] == 200
    status, _ = _request("POST", "/api/muf/auth/logout", _bearer(token))
    assert status == 200
    assert _request("GET", "/api/muf/state", _bearer(token))[0] == 401


def test_auth_start_gives_a_link_into_the_bot(test_db, monkeypatch):
    monkeypatch.setattr(api, "get_bot_username", lambda: "yassirquranbot")
    status, data = _request("POST", "/api/muf/auth/start")
    assert status == 200
    assert data["link"] == ("https://t.me/yassirquranbot?start="
                            + wa.LOGIN_START_PREFIX + data["code"])


def test_poll_waits_until_the_bot_confirms(test_db, monkeypatch):
    monkeypatch.setattr(api, "get_bot_username", lambda: "yassirquranbot")
    _, started = _request("POST", "/api/muf/auth/start")
    code = started["code"]

    status, data = _request("GET", "/api/muf/auth/poll?code=" + code)
    assert status == 200 and data == {"pending": True}

    wa.claim_login_code(code, "12345")
    status, data = _request("GET", "/api/muf/auth/poll?code=" + code)
    assert status == 200
    assert wa.resolve_session(data["token"]) == "12345"


def test_login_attempts_are_capped(test_db, monkeypatch):
    """Заслон от перебора. Порог общий, пока nginx не передаёт настоящий
    адрес клиента (см. _login_rate_ok) - здесь адреса нет, значит проверяем
    именно эту, общую ветку."""
    monkeypatch.setattr(api, "get_bot_username", lambda: "yassirquranbot")
    monkeypatch.setattr(api, "_login_hits", {})
    monkeypatch.setattr(api, "_LOGIN_MAX_PER_HOUR_SHARED", 3)

    for _ in range(3):
        assert _request("POST", "/api/muf/auth/start")[0] == 200
    assert _request("POST", "/api/muf/auth/start")[0] == 429


def test_real_ip_is_counted_per_person(test_db, monkeypatch):
    """Когда nginx передаёт X-Real-IP, лимит считается по каждому отдельно -
    иначе первый же день, когда входят сотни студентов, запер бы всех."""
    monkeypatch.setattr(api, "get_bot_username", lambda: "yassirquranbot")
    monkeypatch.setattr(api, "_login_hits", {})
    monkeypatch.setattr(api, "_LOGIN_MAX_PER_HOUR", 2)

    for _ in range(2):
        assert _request("POST", "/api/muf/auth/start", {"X-Real-IP": "1.1.1.1"})[0] == 200
    assert _request("POST", "/api/muf/auth/start", {"X-Real-IP": "1.1.1.1"})[0] == 429
    # Сосед по подъезду ни при чём
    assert _request("POST", "/api/muf/auth/start", {"X-Real-IP": "2.2.2.2"})[0] == 200
