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
    mk = [c for c in tt.CARDS if c["kind"] == "makhraj"]
    assert all(c["makhraj"] in ids for c in mk)
    assert len({c["id"] for c in tt.CARDS}) == len(tt.CARDS)
    # Нос - место гунны, а не буквы: карточки на него нет, вариантом он есть.
    assert {c["makhraj"] for c in mk} == ids - {"khayshum"}


def test_deck_only_from_published_lessons(test_db):
    _female_like_base()
    glyphs = {c["glyph"] for c in tt.open_cards()}
    assert glyphs == set("ءهعحغخفبموقك")


def test_options_are_four_real_places_with_the_right_one():
    ids = {m["id"] for m in tt.MAKHARIJ}
    for card in (c for c in tt.CARDS if c["kind"] == "makhraj"):
        opts = tt._options(card)
        assert len(opts) == tt.OPTIONS == 4 and len(set(opts)) == 4
        assert card["makhraj"] in opts and set(opts) <= ids
        assert opts == sorted(opts, key=tt._ORDER.get)      # от горла к губам


def test_new_letters_before_repeats(test_db):
    # Пока есть невиданные буквы, выученная сегодня не возвращается: первые
    # 12 карточек - 12 разных букв.
    _female_like_base()
    tt._sessions.clear()
    tt.new_session("777")
    seen = []
    for _ in range(12):
        cur = tt._sessions["777"]["current"]["card"]
        seen.append(cur)
        tt.answer("777", cur, _right_slot("777"))
    assert len(set(seen)) == 12


def _day(monkeypatch, date):
    monkeypatch.setattr(tt, "get_date", lambda: date)


def _row(card):
    return tt._stats("777")[card]


def test_spacing_grows_with_correct_days_and_resets_on_mistake(test_db, monkeypatch):
    # 24.09.2026: «грамотно ответил - зачем их прогонять». Верно с первой
    # попытки - пауза 1, 3, 7... дней; ошибка - снова каждый день.
    _female_like_base()
    _day(monkeypatch, "2026-10-01")
    tt._sessions.clear()
    tt.new_session("777")
    card = tt._sessions["777"]["current"]["card"]
    tt.answer("777", card, _right_slot("777"))
    assert (_row(card)["streak"], _row(card)["due"]) == (1, "2026-10-02")
    # Второй верный в тот же день серию не двигает.
    tt._record("777", card, True, True)
    assert (_row(card)["streak"], _row(card)["due"]) == (1, "2026-10-02")
    _day(monkeypatch, "2026-10-02")
    tt._record("777", card, True, True)
    assert (_row(card)["streak"], _row(card)["due"]) == (2, "2026-10-05")
    _day(monkeypatch, "2026-10-05")
    tt._record("777", card, False, True)
    assert (_row(card)["streak"], _row(card)["due"]) == (0, "2026-10-05")
    # Ответ с повтора после ошибки расписание не трогает.
    tt._record("777", card, True, False)
    assert _row(card)["streak"] == 0


def test_mistaken_letter_goes_first_learned_rests(test_db, monkeypatch):
    _female_like_base()
    _day(monkeypatch, "2026-10-01")
    cards = tt.open_cards("777")
    ids = [c["id"] for c in cards]
    for cid in ids:
        tt._record("777", cid, True, True)          # все выучены сегодня
    _day(monkeypatch, "2026-10-02")
    tt._record("777", ids[5], False, True)          # одну спутал завтра
    batch = tt._pick_batch("777", cards)
    assert batch[0] == ids[5]
    # Остальные с паузой до 02.10 - подошёл срок, идут следом.
    assert set(batch[1:]) <= set(ids)


def test_learned_letters_rest_while_new_ones_wait(test_db, monkeypatch):
    _female_like_base()
    _day(monkeypatch, "2026-10-01")
    cards = tt.open_cards("777")
    learned = [c["id"] for c in cards[:8]]
    for cid in learned:
        tt._record("777", cid, True, True)
    batch = tt._pick_batch("777", cards)
    assert not set(batch) & set(learned)           # новые впереди отдыхающих


def test_old_rows_without_due_are_reviews_not_mistakes(test_db, monkeypatch):
    # Строки до 24.09 без due: не «ошибочные», а пора повторить - новые идут раньше.
    _female_like_base()
    _day(monkeypatch, "2026-10-01")
    cards = tt.open_cards("777")
    with db.db() as c:
        c.execute("INSERT INTO tajweed_card_stats(user_id, card, shown, correct) VALUES('777',?,5,5)",
                  (cards[0]["id"],))
    assert tt._tier(tt._stats("777")[cards[0]["id"]], "2026-10-01") == 2
    assert cards[0]["id"] not in tt._pick_batch("777", cards)


# ── Сифаты (24.09.2026) ────────────────────────────────────────────────────

def test_sifat_bank_matches_the_bayts():
    by = {}
    for c in tt.CARDS:
        if c["kind"] != "makhraj":
            by.setdefault((c["kind"], c["answer"]), set()).add(c["glyph"])
    assert by[("hams", "hams")] == set("فحثهشخصسكت")
    assert len(by[("hams", "jahr")]) == 18
    assert by[("shidda", "shidda")] == set("ءجدقطبكت")
    assert by[("shidda", "tawassut")] == set("لنعمر")
    assert len(by[("shidda", "rakhawa")]) == 15            # 28 - 8 - 5, алифа среди согласных нет
    assert by[("istila", "istila")] == set("خصضغطقظ")
    assert by[("itbaq", "itbaq")] == set("صضطظ")
    assert by[("idhlaq", "idhlaq")] == set("فرمنلب")
    for p in tt.SIFAT:
        assert sum(1 for c in tt.CARDS if c["kind"] == p["id"]) == 28


def test_sifat_pair_opens_with_its_lesson(test_db):
    _female_like_base()
    assert not [c for c in tt.open_cards() if c["kind"] != "makhraj"]
    _lesson("Первая пара: الهمس и الجهر", 6)
    kinds = Counter(c["kind"] for c in tt.open_cards())
    assert kinds["hams"] == 28 and "shidda" not in kinds


def test_sifat_card_asks_its_own_question(test_db):
    _lesson("Первая пара: الهمس и الجهر", 1)
    tt._sessions.clear()
    data = tt.new_session("777")
    assert data["card"]["question"] == "Шёпот или звонкость?"
    assert data["options"] == ["Шёпот — الهمس", "Звонкость — الجهر"]
    card = tt._CARD[data["card"]["id"]]
    slot = tt._sessions["777"]["current"]["options"].index(card["answer"])
    res, _ = tt.answer("777", card["id"], slot)
    assert res["feedback"]["correct"] is True
    assert res["feedback"]["answer"] in data["options"]


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
    assert tt._stats("777")[missed]["shown"] == 1


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
