"""Тренажёр таджвида (14.09.2026): колода только из опубликованных уроков,
буквы идут равномерно, восемь вариантов из всех 17 мест выхода, ошибка
повторяется в конце захода, норма 4 буквы засчитывает задание «j»; группе без
таджвида тренажёр не виден."""

import asyncio
from collections import Counter

import core.db as db
import core.mufradat_api as api
import core.tajweed_trainer as tt
import core.tg as tg


def _group(chat_id="-100902", title="N-1", tasks="m,r,t,j"):
    db.save_group(chat_id, title, tasks=tasks)
    db.update_group_type(chat_id, "relaxed")
    return db.get_group(chat_id)


def _lesson(topic, order, published=True):
    with db.db() as c:
        c.execute(
            "INSERT INTO curriculum_parts(subject, chapter, topic, part_number, part_total,"
            " order_index, content, published_at) VALUES('j','Глава',?,1,1,?,'Текст',?)",
            (topic, order, "2026-07-01" if published else None))


def _female_like_base():
    """Как у сестёр на 14.09: введение, горло, губы, корень языка."""
    _lesson("Сколько всего мест выхода", 1)
    _lesson("Горло (الحلق)", 2)
    _lesson("Губы (الشفتان)", 3)
    _lesson("Корень языка (أقصى اللسان)", 4)
    _lesson("Середина языка (وسط اللسان)", 5, published=False)


def _right_slot(user_id):
    cur = tt._sessions[str(user_id)]["current"]
    return cur["options"].index(tt._CARD[cur["card"]]["makhraj"])


def _wrong_slot(user_id):
    return (_right_slot(user_id) + 1) % tt.OPTIONS


def _call(method, path, user_id, body=None):
    # Уроки в тестах кладутся в базу уже «опубликованными» - открываем их
    # группам с этим предметом, как это сделал бы разовый перенос.
    from core import curriculum
    curriculum.backfill()

    async def run():
        from aiohttp.test_utils import TestClient, TestServer
        client = TestClient(TestServer(api.build_app()))
        await client.start_server()
        try:
            resp = await client.request(method, path, json=body,
                                        headers={"X-Telegram-Init-Data": user_id})
            return resp.status, (await resp.json())
        finally:
            await client.close()
    return asyncio.run(run())


def _auth(monkeypatch, supers=()):
    monkeypatch.setattr(api, "validate_init_data", lambda raw, token: {"id": raw})
    monkeypatch.setattr(api, "SUPER_ADMIN_IDS", list(supers))
    tt._sessions.clear()


def test_bank_is_consistent():
    ids = {m["id"] for m in tt.MAKHARIJ}
    assert len(ids) == 17
    assert all(c["makhraj"] in ids for c in tt.CARDS)
    assert len({c["id"] for c in tt.CARDS}) == len(tt.CARDS)
    # Нос - место гунны, а не буквы: карточки на него нет, вариантом он есть.
    assert {c["makhraj"] for c in tt.CARDS} == ids - {"khayshum"}


def test_deck_only_from_published_lessons(test_db):
    _female_like_base()
    glyphs = {c["glyph"] for c in tt.open_cards()}
    assert glyphs == set("ءهعحغخفبموقك")


def test_options_are_eight_real_places_with_the_right_one():
    ids = {m["id"] for m in tt.MAKHARIJ}
    for card in tt.CARDS:
        opts = tt._options(card)
        assert len(opts) == 8 and len(set(opts)) == 8
        assert card["makhraj"] in opts and set(opts) <= ids
        assert opts == sorted(opts, key=tt._ORDER.get)      # от горла к губам


def test_letters_come_evenly(test_db):
    _female_like_base()
    tt._sessions.clear()
    for _ in range(9):                       # 36 показов на 12 букв
        tt.new_session("777")
        while tt._sessions["777"]["current"]:
            tt.answer("777", tt._sessions["777"]["current"]["card"], _right_slot("777"))
    shown = Counter({c["id"]: 0 for c in tt.open_cards()})
    shown.update(tt._shown_counts("777"))
    assert max(shown.values()) - min(shown.values()) <= 1


def test_mistake_is_repeated_at_the_end_until_right(test_db):
    _female_like_base()
    tt._sessions.clear()
    tt.new_session("777")
    missed = tt._sessions["777"]["current"]["card"]
    data, _ = tt.answer("777", missed, _wrong_slot("777"))
    assert data["feedback"]["correct"] is False
    order = []
    while tt._sessions["777"]["current"]:
        cur = tt._sessions["777"]["current"]["card"]
        order.append(cur)
        slot = _wrong_slot("777") if len(order) == 4 else _right_slot("777")
        data, _ = tt.answer("777", cur, slot)
    # три новые, повтор ошибки (снова мимо), ещё раз повтор - верно
    assert order[3] == missed and order[4] == missed and len(order) == 5
    fin = data["finished"]
    assert fin["size"] == 4 and fin["first_right"] == 3
    assert [x["first"] for x in fin["letters"]] == [False, True, True, True]
    assert fin["letters"][0]["glyph"] == tt._CARD[missed]["glyph"]
    assert tt._shown_counts("777")[missed] == 1
    assert data["daily_count"] == 4


def test_four_letters_credit_tajweed_once_and_tell_the_group(test_db, monkeypatch):
    _auth(monkeypatch)
    sent = []

    async def fake_send(chat_id, text, **kw):
        sent.append((chat_id, text))
    monkeypatch.setattr(tg, "send_message", fake_send)
    g = _group()
    sid = db.add_student("Сатар", g["id"], phone="777")
    _female_like_base()

    status, data = _call("GET", "/api/muf/tajweed", "777")
    assert status == 200 and len(data["options"]) == 8
    assert data["task"] == {"done": False}
    for _ in range(4):
        card = data["card"]["id"]
        _, data = _call("POST", "/api/muf/tajweed/answer", "777",
                        {"card": card, "slot": _right_slot("777")})
    assert data["finished"] and data["daily_count"] == 4
    assert data["task"] == {"done": True}
    assert db.get_today_report(sid, g["id"])["j"] is True
    assert sent == [(g["chat_id"], "Сатар, Таджвид + (через тренажёр).")]

    _, data = _call("POST", "/api/muf/tajweed/new", "777")
    for _ in range(4):
        _, data = _call("POST", "/api/muf/tajweed/answer", "777",
                        {"card": data["card"]["id"], "slot": _right_slot("777")})
    assert len(sent) == 1                      # второй раз группе не пишем


def test_hidden_for_group_without_tajweed_but_open_for_ustaz(test_db, monkeypatch):
    _auth(monkeypatch)
    g = _group(tasks="m,r,t")
    db.add_student("Абдулла", g["id"], phone="777")
    db.add_group_admin(g["id"], "555")
    _female_like_base()

    status, _ = _call("GET", "/api/muf/tajweed", "777")
    assert status == 403
    assert api._dashboard_facts("777")["tajweed"] is None

    status, data = _call("GET", "/api/muf/tajweed", "555")
    assert status == 200 and data["task"] is None
    assert api._dashboard_facts("555")["tajweed"] == {"done": 0, "target": 4}
