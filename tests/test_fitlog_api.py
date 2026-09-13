"""Отчёт о поздней перепроверке кегля мусхафа (13.09.2026).

Приложение шлёт его, когда подгонка через полсекунды-полторы дала другой
размер, чем первая (на айфонах первый замер идёт по тексту без шрифта
страницы - document.fonts.ready в WebKit приходит до раскладки). Сервер
только пишет строку в журнал - по ней после выкладки видно, на каких
телефонах замер врёт."""

import asyncio
import logging

import core.mufradat_api as api


def _post(make_app, path, user_id, body):
    async def run():
        from aiohttp.test_utils import TestClient, TestServer
        client = TestClient(TestServer(make_app()))
        await client.start_server()
        try:
            resp = await client.request(
                "POST", path, json=body,
                headers={"X-Telegram-Init-Data": user_id,
                         "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X)"})
            return resp.status, (await resp.json())
        finally:
            await client.close()
    return asyncio.run(run())


def _setup(monkeypatch):
    monkeypatch.setattr(api, "validate_init_data", lambda raw, token: {"id": raw})
    return api.build_app


def test_fitlog_writes_one_journal_line(test_db, monkeypatch, caplog):
    make_app = _setup(monkeypatch)
    with caplog.at_level(logging.INFO, logger="core.mufradat_api"):
        status, data = _post(make_app, "/api/muf/fitlog", "201", {
            "page": 6, "lines": 15, "avail": 374,
            "first": 34.0, "first_why": "frame", "first_capped": True,
            "final": 22.4, "final_why": "500ms",
        })
    assert (status, data) == (200, {"ok": True})
    lines = [r.getMessage() for r in caplog.records if "fitlog" in r.getMessage()]
    assert len(lines) == 1
    assert "user=201 page=6 lines=15 avail=374" in lines[0]
    assert "first=34.0/frame capped final=22.4/500ms iOS 18.7" in lines[0]


def test_fitlog_rejects_garbage(test_db, monkeypatch):
    make_app = _setup(monkeypatch)
    status, data = _post(make_app, "/api/muf/fitlog", "201", {"page": "six"})
    assert status == 400
    assert data == {"error": "bad_body"}


def test_ua_short():
    assert api._ua_short("Mozilla/5.0 (iPhone; CPU iPhone OS 18_7_8 like Mac OS X) CriOS/153") == "iOS 18.7"
    assert api._ua_short("Mozilla/5.0 (Linux; Android 14; Pixel 7) Chrome/128") == "Android 14"
    assert api._ua_short("Mozilla/5.0 (Windows NT 10.0)") == "other"
