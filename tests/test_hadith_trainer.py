"""Тренажёр хадисов (23.09.2026): слово дня внутри фразы, закрепление с
четырьмя вариантами в обе стороны, норма 5 верных (в начале меньше: одно
слово - 2, два - 4), ошибка возвращается другой стороной, одно новое слово
в день, старт с любого хадиса и слова."""
import core.hadith_trainer as ht


def _answer_right(uid):
    s = ht._load_session(uid)
    cur = s["current"]
    return ht.answer(uid, cur["id"], cur["right"])


def _answer_wrong(uid):
    s = ht._load_session(uid)
    cur = s["current"]
    wrong = next(o["key"] for o in cur["options"] if o["key"] != cur["right"])
    return ht.answer(uid, cur["id"], wrong)


def test_data_has_all_hadiths_with_words():
    d = ht.data()
    assert sorted(d) == list(range(1, 43))
    assert all(h["words"] and all(w["ar"] and w["ru"] for w in h["words"]) for h in d.values())
    first = [w["ar"] for w in d[1]["words"][:3]]
    assert first == ["إنَّمَا", "الْأَعْمَالُ", "بِالنِّيَّاتِ"]


def test_first_open_asks_where_to_start(test_db):
    st = ht.state("1")
    assert len(st["pick"]) == 42 and "new_word" not in st


def test_new_word_is_shown_inside_its_phrase(test_db):
    ht.set_start("1", 1, 0)
    st = ht.state("1")
    w = st["new_word"]
    assert w["ar"] == "إنَّمَا" and w["ru"] == "Поистине" and w["pos"] == 1
    hl = [t["t"] for t in w["context"]["tokens"] if t["hl"]]
    assert len(hl) == 1 and "إنَّمَا" in hl[0]


def test_first_word_ever_norm_is_two_both_directions(test_db):
    ht.set_start("1", 1, 0)
    st = ht.learn("1")
    assert st["daily_target"] == 2 and st["card"]["size"] == 2
    dirs = [st["card"]["dir"]]
    st, _ = _answer_right("1")
    dirs.append(st["card"]["dir"])
    assert sorted(dirs) == ["ar2ru", "ru2ar"]
    st, reached = _answer_right("1")
    assert reached and st["finished"]["correct"] == 2


def test_norm_is_five_once_three_words_known(test_db):
    ht.set_start("1", 1, 5)                  # продолжает с 6-го слова
    st = ht.learn("1")
    assert st["daily_target"] == 5 and st["card"]["size"] == 5
    reached_at = None
    for k in range(5):
        st, reached = _answer_right("1")
        if reached:
            reached_at = k + 1
    assert reached_at == 5 and "finished" in st


def test_options_are_four_and_distinct(test_db):
    ht.set_start("1", 1, 10)
    st = ht.learn("1")
    opts = st["card"]["options"]
    assert len(opts) == 4 and len({o["key"] for o in opts}) == 4


def test_wrong_answer_comes_back_other_direction(test_db):
    ht.set_start("1", 1, 10)
    ht.learn("1")
    first = ht._load_session("1")["current"]
    _answer_wrong("1")
    q = ht._load_session("1")["queue"]
    assert q[-1][:2] == [first["n"], first["i"]] and q[-1][2] != first["dir"]


def test_only_one_new_word_a_day(test_db):
    """Правило методики: одно новое слово в день, «ещё слова» нет."""
    ht.set_start("1", 1, 10)
    st = ht.learn("1")
    while st.get("card"):
        st, _ = _answer_right("1")
    assert st["finished"]["more"] is False
    assert "new_word" not in ht.more("1")
    assert ht.new_today("1") == 1
    st = ht.restart("1")
    assert st.get("card")                      # повтор выученного - можно


def test_finishing_a_hadith_moves_to_the_next(test_db):
    last = len(ht.data()[1]["words"]) - 1
    ht.set_start("1", 1, last)
    ht.learn("1")
    assert ht.progress("1") == (2, 0)


def test_repeated_word_counts_once_in_pool(test_db):
    """«إلى — к» в первом хадисе трижды - в пуле одно слово."""
    ht.set_start("1", 1, 31)
    idents = [ht._identity(n, i) for n, i in ht.learned("1")]
    assert len(set(idents)) < len(idents)


# ── API: доступ по заданию «h», зачёт в группе ───────────────────────────────

import asyncio

import core.db as db
import core.mufradat_api as api
import core.tg as tg


def _call(method, path, user_id, body=None):
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


def _group(tasks="m,r,t,j,n,h"):
    db.save_group("-100902", "N-1", tasks=tasks)
    db.update_group_type("-100902", "pro")
    return db.get_group("-100902")


def test_norm_credits_hadith_once_and_tells_the_group(test_db, monkeypatch):
    monkeypatch.setattr(api, "validate_init_data", lambda raw, token: {"id": raw})
    monkeypatch.setattr(api, "SUPER_ADMIN_IDS", [])
    sent = []

    async def fake_send(chat_id, text, **kw):
        sent.append((chat_id, text))
    monkeypatch.setattr(tg, "send_message", fake_send)
    g = _group()
    sid = db.add_student("Ибрахим", g["id"], phone="777")

    status, data = _call("GET", "/api/muf/hadith", "777")
    assert status == 200 and len(data["pick"]) == 42 and data["task"] == {"done": False}
    status, words = _call("GET", "/api/muf/hadith/words?n=8", "777")
    assert status == 200 and len(words["words"]) > 10
    _, data = _call("POST", "/api/muf/hadith/start", "777", {"hadith": 8, "pos": 9})
    assert data["new_word"]["hadith"] == 8 and data["new_word"]["pos"] == 10
    _, data = _call("POST", "/api/muf/hadith/learn", "777")
    while data.get("card"):
        cur = ht._load_session("777")["current"]
        _, data = _call("POST", "/api/muf/hadith/answer", "777", {"card": cur["id"], "choice": cur["right"]})
    assert data["daily_count"] == 5 and data["task"] == {"done": True}
    assert db.get_today_report(sid, g["id"])["h"] is True
    assert sent == [(g["chat_id"], "Ибрахим, Хадис + (через тренажёр).")]


def test_hidden_for_group_without_hadith_but_open_for_ustaz(test_db, monkeypatch):
    monkeypatch.setattr(api, "validate_init_data", lambda raw, token: {"id": raw})
    monkeypatch.setattr(api, "SUPER_ADMIN_IDS", [])
    g = _group(tasks="m,r,t,j,n")
    db.add_student("Абдулла", g["id"], phone="777")
    db.add_group_admin(g["id"], "555")
    assert _call("GET", "/api/muf/hadith", "777")[0] == 403
    assert api._dashboard_facts("777")["hadith"] is None
    assert _call("GET", "/api/muf/hadith", "555")[0] == 200
    assert api._dashboard_facts("555")["hadith"] == {"done": 0, "target": 5}


def test_old_words_come_mostly_from_the_current_hadith(test_db):
    """Начал с 8-го: прежние хадисы - не больше одного слова за заход."""
    ht.set_start("1", 8, 9)
    ht.learn("1")
    q = ht._load_session("1")
    words = [tuple(x[:2]) for x in q["queue"]] + [(q["current"]["n"], q["current"]["i"])]
    assert sum(1 for n, _ in set(words) if n != 8) <= 1


def test_summary_lists_each_word_once(test_db):
    ht.set_start("1", 1, 10)
    st = ht.learn("1")
    while st.get("card"):
        st, _ = _answer_right("1")
    keys = [r["key"] for r in st["finished"]["results"]]
    assert len(keys) == len(set(keys))
