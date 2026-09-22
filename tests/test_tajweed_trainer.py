"""Тренажёр таджвида (14.09.2026): колода только из опубликованных уроков,
буквы идут равномерно, OPTIONS (четыре) варианта из всех 17 мест выхода, норма 4 буквы
засчитывает задание «j»; группе без таджвида тренажёр не виден.

С 20.09.2026 карточки идут ЛЕНТОЙ: экрана «Заход окончен» с кнопкой «Ещё
заход» больше нет (решение пользователя — он вставал стеной каждые четыре
буквы и спрашивал разрешения продолжить). Ошибка возвращается через три
карточки, а не «в конец захода»."""

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


def test_options_are_four_real_places_with_the_right_one():
    ids = {m["id"] for m in tt.MAKHARIJ}
    for card in tt.CARDS:
        opts = tt._options(card)
        assert len(opts) == tt.OPTIONS == 4 and len(set(opts)) == 4
        assert card["makhraj"] in opts and set(opts) <= ids
        assert opts == sorted(opts, key=tt._ORDER.get)      # от горла к губам


def test_letters_come_evenly(test_db):
    # Равномерность держится и без границ захода: подбор доливает те буквы,
    # что показывались реже всех.
    _female_like_base()
    tt._sessions.clear()
    tt.new_session("777")
    for _ in range(36):                      # 36 показов на 12 букв
        tt.answer("777", tt._sessions["777"]["current"]["card"], _right_slot("777"))
    shown = Counter({c["id"]: 0 for c in tt.open_cards()})
    shown.update(tt._shown_counts("777"))
    assert max(shown.values()) - min(shown.values()) <= 1


def test_the_stream_never_stops(test_db):
    # Ради чего всё: после нормы дня приходит следующая карточка, а не экран
    # «Заход окончен» с кнопкой «Ещё заход».
    _female_like_base()
    tt._sessions.clear()
    tt.new_session("777")
    for _ in range(20):                      # впятеро больше нормы дня
        card = tt._sessions["777"]["current"]["card"]
        data, _ = tt.answer("777", card, _right_slot("777"))
        assert "finished" not in data
        assert data["card"]["id"]
    assert data["daily_count"] >= tt.DAILY_TARGET
    assert data["card"]["day_done"] is True
    # Точки показывают ход ДНЯ, а не место внутри порции.
    assert data["card"]["size"] == tt.DAILY_TARGET


def test_mistake_comes_back_three_cards_later(test_db):
    # Ошибка возвращается не сразу и не «в конце захода», а через три
    # карточки: подряд — это проверка памяти на пять секунд, а не знания
    # места выхода.
    _female_like_base()
    tt._sessions.clear()
    tt.new_session("777")
    missed = tt._sessions["777"]["current"]["card"]
    data, _ = tt.answer("777", missed, _wrong_slot("777"))
    assert data["feedback"]["correct"] is False

    order = []
    for _ in range(4):
        cur = tt._sessions["777"]["current"]["card"]
        order.append(cur)
        data, _ = tt.answer("777", cur, _right_slot("777"))

    assert missed not in order[:3]                   # не сразу
    assert order[3] == missed                        # ровно через три
    assert data["card"]["retry"] is False            # ответил верно — метка снята
    # Показ считается один раз: повтор ошибки не раздувает счётчик, иначе
    # равномерность подбора перекосило бы в сторону ошибочных букв.
    assert tt._shown_counts("777")[missed] == 1


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
    assert status == 200 and len(data["options"]) == 4
    assert data["task"] == {"done": False}
    for _ in range(4):
        card = data["card"]["id"]
        _, data = _call("POST", "/api/muf/tajweed/answer", "777",
                        {"card": card, "slot": _right_slot("777")})
    assert data["daily_count"] == 4 and data["card"]["day_done"] is True
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


def test_mistake_on_the_last_card_of_a_batch_also_waits(test_db):
    """Находка 20.09: на последней карточке порции очередь пуста, вставка
    «через три» превращалась в позицию 0 — и буква приходила следующим же
    вопросом. При порции в четыре буквы это каждая четвёртая ошибка."""
    _female_like_base()
    tt._sessions.clear()
    tt.new_session("777")
    # Три верных — очередь порции пуста, четвёртая карточка последняя.
    for _ in range(3):
        tt.answer("777", tt._sessions["777"]["current"]["card"], _right_slot("777"))
    assert tt._sessions["777"]["queue"] == []

    missed = tt._sessions["777"]["current"]["card"]
    tt.answer("777", missed, _wrong_slot("777"))

    order = []
    for _ in range(4):
        cur = tt._sessions["777"]["current"]["card"]
        order.append(cur)
        tt.answer("777", cur, _right_slot("777"))

    assert missed not in order[:3]
    assert order[3] == missed
