"""Тренажёр нахва (17.09.2026): ответы из разметки корпуса, повтор ошибки -
другое слово того же типа, ступень 2 открывается после 85% на 40 ответах,
норма 10 верных засчитывает «n»; группе без нахва тренажёр не виден."""

import asyncio

import core.db as db
import core.mufradat_api as api
import core.nahw_trainer as nt
import core.tg as tg


def _group(chat_id="-100903", title="N-2a", tasks="m,r,t,j,n"):
    db.save_group(chat_id, title, tasks=tasks)
    db.update_group_type(chat_id, "relaxed")
    return db.get_group(chat_id)


def _lesson(topic="أنواع الكلمة (Виды слова)", published=True):
    with db.db() as c:
        c.execute(
            "INSERT INTO curriculum_parts(subject, chapter, topic, part_number, part_total,"
            " order_index, content, published_at) VALUES('n','الكلمة',?,1,1,1,'Текст',?)",
            (topic, "2026-07-01" if published else None))


def _no_sources(monkeypatch):
    """Текст аятов - из разметки, а не из sources/hadiths.db (в CI её нет)."""
    def fake_words(surah, ayah):
        a = nt.corpus().ayat["%d:%d" % (surah, ayah)]
        return [(int(p), "".join(s[0] for s in a[p]), "смысл") for p in sorted(a, key=int)]
    monkeypatch.setattr(nt, "_ayah_words", fake_words)
    monkeypatch.setattr(nt, "_pool_limit", lambda user_id: nt.corpus().ord["2:29"])


def _current(user_id):
    return nt._load_session(user_id)["current"]


def _right(user_id):
    return nt.CTYPES[_current(user_id)["ctype"]][0]


def _wrong(user_id):
    return next(a for a in nt.ANSWERS if a != _right(user_id))


def _item(ref):
    s, a, w = ref.split(":")
    return nt.corpus().ayat["%s:%s" % (s, a)][w]


def _ctype(ref, idx):
    s, a, w = ref.split(":")
    ayah = nt.corpus().ayat["%s:%s" % (s, a)]
    return nt._classify(ayah[w], idx, ayah, int(w))


def test_classification_follows_lesson_signs():
    assert _ctype("1:2:1", 1) == ("ism_al", 1)          # ٱلْحَمْدُ
    assert _ctype("1:5:2", 0) == ("fil_mudari", 1)      # نَعْبُدُ
    assert _ctype("1:7:4", 0) == ("c_harf", 2)          # عَلَيْ + هِمْ
    assert _ctype("2:20:19", 0) == ("c_harf_pref", 2)   # وَ + أَبْصَٰرِ + هِمْ
    assert _ctype("2:20:19", 1) == ("c_ism", 2)
    assert _ctype("2:20:19", 2) is None                 # ضمير - не в этом уроке
    assert _ctype("2:2:1", 0) is None                   # ذَٰلِكَ - указательное
    assert _ctype("2:10:9", 0) == ("ism_tanwin", 1)     # أَلِيمٌۢ
    assert _ctype("1:2:1", 0) is None                   # ال - признак, не вопрос


def test_every_indexed_item_has_its_answer_kind():
    kinds = {"ism": "N", "fil": "V", "harf": "P"}
    for ctype, (ords, items) in nt.corpus().index.items():
        assert ords == sorted(ords)
        for item in items[:200]:
            _, word, _, idx = nt.corpus().word(item)
            assert word[idx][1] == kinds[nt.CTYPES[ctype][0]], (ctype, item)


def test_name_of_allah_is_never_asked():
    """Проверка по буквам, не по записи с харакатами: 17.09.2026 исключение
    по строке «LEM:اللَّه» молча не срабатывало из-за порядка шадды и фатхи."""
    asked = [item for _, items in nt.corpus().index.values() for item in items
             if nt._letters(nt.corpus().word(item)[1][nt.corpus().word(item)[3]][0]) in ("الله", "لله", "اللهم")]
    assert asked == []
    assert _ctype("2:61:50", 0) is None


def test_compound_word_is_split_on_our_spelling():
    parts = nt.split_by_segments("وَأَبْصَٰرِهِمْ", _item("2:20:19"))
    assert parts == ["وَ", "أَبْصَٰرِ", "هِمْ"]
    # выпавшее местоимение (رَبِّ «мой Господь») - пустая часть, не отказ
    assert nt.split_by_segments("رَبِّ", [["رَبِّ", "N", "LEM:رَبّ"], ["", "N", "PRON|SUFF|1S"]]) == ["رَبِّ", ""]


def test_explanation_uses_lesson_words():
    assert nt.explain("1:2:1:1") == "Есть артикль الـ — признак исма."
    assert nt.explain("1:5:2:0") == "Действие в настоящем или будущем — это фиаль."


def test_nothing_without_published_lesson(test_db, monkeypatch):
    _no_sources(monkeypatch)
    _lesson(published=False)
    assert nt.state("777")["empty"] is True


def test_mistake_repeats_with_another_word_of_the_same_type(test_db, monkeypatch):
    _no_sources(monkeypatch)
    _lesson()
    nt.new_session("777")
    first = _current("777")
    data, _ = nt.answer("777", first["item"], _wrong("777"))
    assert data["feedback"]["correct"] is False and data["feedback"]["explain"]
    seen = [first["item"]]
    while _current("777") and not _current("777")["retry"]:
        cur = _current("777")
        seen.append(cur["item"])
        nt.answer("777", cur["item"], _right("777"))
    retry = _current("777")
    assert retry["ctype"] == first["ctype"] and retry["item"] not in seen
    data, _ = nt.answer("777", retry["item"], _right("777"))
    fin = data["finished"]
    assert fin["size"] == nt.SESSION_SIZE
    assert nt.CTYPES[first["ctype"]][1] in fin["weak"]
    assert data["daily_count"] == nt.SESSION_SIZE        # 9 сразу + 1 с повтора


def test_session_survives_restart(test_db, monkeypatch):
    _no_sources(monkeypatch)
    _lesson()
    before = nt.state("777")["card"]["id"]
    assert nt.state("777")["card"]["id"] == before       # из базы, не из памяти


def test_stage_two_opens_after_85_percent_of_40(test_db, monkeypatch):
    _no_sources(monkeypatch)
    _lesson()
    assert nt.stage_of("777") == 1
    for i in range(4):
        nt.new_session("777")
        n = 0
        while _current("777"):
            choice = _wrong("777") if (i == 0 and n < 6) else _right("777")
            nt.answer("777", _current("777")["item"], choice)
            n += 1
    assert nt.stage_of("777") == 2
    nt.new_session("777")
    assert nt._load_session("777")["stage"] == 2


def test_ten_right_credit_nahw_once_and_tell_the_group(test_db, monkeypatch):
    _no_sources(monkeypatch)
    monkeypatch.setattr(api, "validate_init_data", lambda raw, token: {"id": raw})
    monkeypatch.setattr(api, "SUPER_ADMIN_IDS", [])
    sent = []

    async def fake_send(chat_id, text, **kw):
        sent.append((chat_id, text))
    monkeypatch.setattr(tg, "send_message", fake_send)
    g = _group()
    sid = db.add_student("Сатар", g["id"], phone="777")
    _lesson()

    status, data = _call("GET", "/api/muf/nahw", "777")
    assert status == 200 and [o["key"] for o in data["options"]] == ["ism", "fil", "harf"]
    assert data["task"] == {"done": False}
    while data.get("card"):
        _, data = _call("POST", "/api/muf/nahw/answer", "777",
                        {"card": data["card"]["id"], "choice": _right("777")})
    assert data["daily_count"] == 10 and data["task"] == {"done": True}
    assert db.get_today_report(sid, g["id"])["n"] is True
    assert sent == [(g["chat_id"], "Сатар, Нахв + (через тренажёр).")]

    _, data = _call("POST", "/api/muf/nahw/new", "777")
    _, data = _call("POST", "/api/muf/nahw/answer", "777",
                    {"card": data["card"]["id"], "choice": _right("777")})
    assert len(sent) == 1


def test_hidden_for_group_without_nahw_but_open_for_ustaz(test_db, monkeypatch):
    _no_sources(monkeypatch)
    monkeypatch.setattr(api, "validate_init_data", lambda raw, token: {"id": raw})
    monkeypatch.setattr(api, "SUPER_ADMIN_IDS", [])
    g = _group(tasks="m,r,t,j")
    db.add_student("Абдулла", g["id"], phone="777")
    db.add_group_admin(g["id"], "555")
    _lesson()

    assert _call("GET", "/api/muf/nahw", "777")[0] == 403
    assert api._dashboard_facts("777")["nahw"] is None
    status, data = _call("GET", "/api/muf/nahw", "555")
    assert status == 200 and data["task"] is None
    assert api._dashboard_facts("555")["nahw"] == {"done": 0, "target": 10}


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
