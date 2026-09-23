"""Дубль объявлений мужского Тадаббура сёстрам (23.09.2026,
core/tadabbur_mirror.py)."""
import asyncio
import os

import pytest

import config
import core.db as db
import core.tadabbur_mirror as tm

TAD = "-100777004"
ADMIN = "272581710"


@pytest.fixture
def env(test_db, test_hadiths_db, monkeypatch):
    db.save_group(TAD, "Yassir Тадаббур", tasks="m,r,t")
    db.update_group_type(TAD, "tadabbur")
    monkeypatch.setattr(config, "SUPER_ADMIN_IDS", [ADMIN])
    monkeypatch.setattr(config, "PROFILE", "male")
    return monkeypatch


def _msg(mid=1, sender=ADMIN, chat=TAD, **extra):
    m = {"message_id": mid, "chat": {"id": int(chat)}, "from": {"id": int(sender)}}
    m.update(extra)
    return m


def test_берёт_только_суперадмина_в_тадаббуре_без_реплая(env):
    assert tm.should_mirror(_msg(text="Объявление"))
    assert not tm.should_mirror(_msg(sender="111", text="привет"))
    assert not tm.should_mirror(_msg(chat="-100555", text="в другой группе"))
    assert not tm.should_mirror(_msg(text="ответ", reply_to_message={"message_id": 5}))
    assert not tm.should_mirror(_msg(text="   "))
    assert not tm.should_mirror(_msg(sticker={"file_id": "s"}))


def test_женский_бот_сам_ничего_не_берёт(env):
    env.setattr(config, "PROFILE", "female")
    assert not tm.should_mirror(_msg(text="Объявление"))


def test_текст_уходит_один_раз(env):
    assert asyncio.run(tm.enqueue(_msg(7, text="Новое в приложении")))
    assert not asyncio.run(tm.enqueue(_msg(7, text="Новое в приложении")))   # повтор апдейта

    env.setattr(config, "PROFILE", "female")
    sent = []

    async def fake_call(method, payload=None, timeout=35):
        sent.append((method, payload))
        return {"ok": True, "result": {"message_id": 1}}
    import core.tg as tg
    env.setattr(tg, "tg_call", fake_call)
    assert asyncio.run(tm.deliver_once()) == 1
    assert sent == [("sendMessage", {"chat_id": TAD, "text": "Новое в приложении"})]
    assert asyncio.run(tm.deliver_once()) == 0          # второй раз не шлёт


def test_фото_скачивается_и_файл_удаляется_после_отправки(env):
    async def fake_download(file_id):
        return b"JPEG", "photo.jpg"
    env.setattr(tm, "_download", fake_download)
    asyncio.run(tm.enqueue(_msg(9, photo=[{"file_id": "small"}, {"file_id": "big"}],
                                caption="Скрин настроек")))
    with tm._connect() as c:
        row = c.execute("SELECT * FROM tadabbur_mirror").fetchone()
    assert row["kind"] == "photo" and row["text"] == "Скрин настроек"
    assert os.path.exists(row["file_path"])

    got = []

    async def fake_send(chat_id, r):
        got.append((chat_id, r["kind"], r["text"]))
        return {"ok": True}
    env.setattr(tm, "_send", fake_send)
    assert asyncio.run(tm.deliver_once()) == 1
    assert got == [(TAD, "photo", "Скрин настроек")]
    assert not os.path.exists(row["file_path"])


def test_сбой_повторяется_не_больше_трёх_раз(env):
    asyncio.run(tm.enqueue(_msg(3, text="x")))
    calls = []

    async def failing(chat_id, r):
        calls.append(1)
        return {"ok": False, "description": "Forbidden"}
    env.setattr(tm, "_send", failing)
    for _ in range(5):
        asyncio.run(tm.deliver_once())
    assert len(calls) == tm.MAX_ATTEMPTS


def test_старое_не_всплывает(env):
    asyncio.run(tm.enqueue(_msg(4, text="вчерашнее")))
    with tm._connect() as c:
        c.execute("UPDATE tadabbur_mirror SET created_at='2026-01-01T00:00:00+06:00'")

    async def must_not_send(chat_id, r):
        raise AssertionError("не должно уходить")
    env.setattr(tm, "_send", must_not_send)
    assert asyncio.run(tm.deliver_once()) == 0
