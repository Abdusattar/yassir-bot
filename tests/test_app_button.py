"""Кнопка приложения лично в чат лички (20.10.2026, core/tg.py)."""
import asyncio

import config
import core.tg as tg


def _run(monkeypatch, chats, profile="female"):
    calls = []

    async def fake_call(method, payload=None, timeout=35):
        calls.append((method, payload))
        return {"ok": True}
    monkeypatch.setattr(tg, "tg_call", fake_call)
    monkeypatch.setattr(tg, "APP_BUTTON", True)
    monkeypatch.setattr(tg, "_app_button_set", set())
    monkeypatch.setattr(config, "PROFILE", profile)
    monkeypatch.setattr(config, "MUSHAF_URL", "https://yassirilm.com/")

    async def go():
        for c in chats:
            await tg.ensure_app_button(c)
    asyncio.run(go())
    return calls


def test_button_set_once_per_chat(monkeypatch):
    calls = _run(monkeypatch, ["8922609616", 8922609616, "8922609616"])
    assert len(calls) == 1
    method, payload = calls[0]
    assert method == "setChatMenuButton"
    assert payload["chat_id"] == 8922609616
    assert payload["menu_button"]["web_app"]["url"] == "https://yassirilm.com/?bot=female"


def test_own_half_in_url(monkeypatch):
    calls = _run(monkeypatch, ["1"], profile="male")
    assert calls[0][1]["menu_button"]["web_app"]["url"].endswith("?bot=male")


def test_groups_skipped(monkeypatch):
    assert _run(monkeypatch, ["-1003503925527", "", None]) == []


def test_off_switch(monkeypatch):
    calls = []

    async def fake_call(method, payload=None, timeout=35):
        calls.append(method)
    monkeypatch.setattr(tg, "tg_call", fake_call)
    monkeypatch.setattr(tg, "_app_button_set", set())
    asyncio.run(tg.ensure_app_button("5"))   # conftest выключил
    assert calls == []
