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
    return nt.right_answer(_current(user_id))


def _wrong(user_id):
    skill = nt._SKILL[_current(user_id)["skill"]]
    return next(o["key"] for o in skill["options"] if o["key"] != _right(user_id))


def _card_id(user_id):
    cur = _current(user_id)
    return cur["skill"] + "|" + cur["item"]


def _item(ref):
    s, a, w = ref.split(":")
    return nt.corpus().ayat["%s:%s" % (s, a)][w]


def _ctype(ref, idx, skill="kinds"):
    s, a, w = ref.split(":")
    ayah = nt.corpus().ayat["%s:%s" % (s, a)]
    return nt._SKILL[skill]["classify"](ayah[w], idx, ayah, int(w))


def test_classification_follows_lesson_signs():
    assert _ctype("1:2:1", 1) == "ism_al"          # ٱلْحَمْدُ
    assert _ctype("1:5:2", 0) == "fil_mudari"      # نَعْبُدُ
    assert _ctype("1:7:4", 0) == "c_harf"          # عَلَيْ + هِمْ
    assert _ctype("2:20:19", 0) == "c_harf_pref"   # وَ + أَبْصَٰرِ + هِمْ
    assert _ctype("2:20:19", 1) == "c_ism"
    assert _ctype("2:20:19", 2) is None                 # ضمير - не в этом уроке
    assert _ctype("2:2:1", 0) is None                   # ذَٰلِكَ - указательное
    assert _ctype("2:10:9", 0) == "ism_tanwin"     # أَلِيمٌۢ
    assert _ctype("1:2:1", 0) is None                   # ال - признак, не вопрос


def test_every_indexed_item_has_its_answer_kind():
    kinds = {"ism": "N", "fil": "V", "harf": "P"}
    for ctype, (ords, items) in nt.corpus().index["kinds"].items():
        assert ords == sorted(ords)
        for item in items[:200]:
            _, word, _, idx = nt.corpus().word(item)
            assert word[idx][1] == kinds[nt._SKILL["kinds"]["ctypes"][ctype][0]], (ctype, item)


def test_index_matches_skills_and_every_type_has_explanation():
    assert set(nt.corpus().index) == {s["id"] for s in nt.SKILLS}
    for skill in nt.SKILLS:
        keys = {o["key"] for o in skill["options"]}
        assert set(nt.corpus().index[skill["id"]]) <= set(skill["ctypes"])
        for ctype, (ans, label) in skill["ctypes"].items():
            assert ans in keys and label
            assert skill["id"] == "kinds" or ctype in nt._EXPLAIN


def test_later_skills_take_only_unambiguous_words():
    assert _ctype("1:2:1", 1, "signs") == "sg_al"              # ٱلْحَمْدُ
    assert _ctype("1:2:4", 1, "number") == "nm_p"              # ٱلْعَٰلَمِينَ
    assert _ctype("1:5:2", 0, "tense") == "tn_mudari"          # نَعْبُدُ
    assert _ctype("1:5:2", 0, "bina") == "bn_mudari"
    assert _ctype("1:5:2", 0, "irab") == "ir_vind"
    assert _ctype("1:6:1", 0, "bina") == "bn_amr"              # ٱهْدِنَا
    assert _ctype("1:6:1", 1, "bina") == "bn_pron"
    assert _ctype("1:7:4", 0, "bina") == "bn_harf"             # عَلَيْهِمْ
    assert _ctype("1:2:1", 1, "defin") == "df_al"
    assert _ctype("2:10:9", 0, "defin") == "df_indef"          # أَلِيمٌۢ
    assert _ctype("1:2:1", 1, "irab") == "ir_nom"
    for skill in nt.SKILLS:                                     # имя Аллаха - нигде
        assert _ctype("2:61:50", 0, skill["id"]) is None


def test_name_of_allah_is_never_asked():
    """Проверка по буквам, не по записи с харакатами: 17.09.2026 исключение
    по строке «LEM:اللَّه» молча не срабатывало из-за порядка шадды и фатхи."""
    asked = []
    for types in nt.corpus().index.values():
        for _, items in types.values():
            asked += [i for i in items
                      if nt._letters(nt.corpus().word(i)[1][nt.corpus().word(i)[3]][0]) in ("الله", "لله", "اللهم")]
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
    # пул пошире: на 29 аятах у редкого типа (фиаль с تْ) другого слова может не быть
    monkeypatch.setattr(nt, "_pool_limit", lambda user_id: nt.corpus().ord["2:141"])
    _lesson()
    nt.new_session("777")
    first = _current("777")
    data, _ = nt.answer("777", _card_id("777"), _wrong("777"))
    assert data["feedback"]["correct"] is False and data["feedback"]["explain"]
    seen = [first["item"]]
    while _current("777") and not _current("777")["retry"]:
        cur = _current("777")
        seen.append(cur["item"])
        nt.answer("777", _card_id("777"), _right("777"))
    retry = _current("777")
    assert retry["ctype"] == first["ctype"] and retry["item"] not in seen
    data, _ = nt.answer("777", _card_id("777"), _right("777"))
    fin = data["finished"]
    assert fin["size"] == nt.SESSION_SIZE
    assert nt._SKILL["kinds"]["ctypes"][first["ctype"]][1] in fin["weak"]
    assert data["daily_count"] == nt.SESSION_SIZE        # 9 сразу + 1 с повтора


def test_session_saved_by_old_version_starts_over(test_db, monkeypatch):
    """17.09.2026: после выкладки навыков у всех, кто начал заход раньше,
    экран висел на «Загрузке» - в старом заходе карточка без «skill»."""
    import json
    _no_sources(monkeypatch)
    _lesson()
    old = {"skill": "kinds", "stage": 1, "size": 10, "asked": 1, "retry": [], "used": ["1:2:1:1"],
           "results": [], "current": {"item": "1:2:1:1", "ctype": "ism_al", "retry": False,
                                      "left": 0, "stage": 1}}
    nt._save_session("777", old)
    data = nt.state("777")
    assert data["card"]["id"].startswith("kinds|")


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
            nt.answer("777", _card_id("777"), choice)
            n += 1
    assert nt.stage_of("777") == 2
    nt.new_session("777")
    assert nt._load_session("777")["stage"] == 2


def _answer_all(user_id, passed=0, rounds=1):
    data = None
    for _ in range(rounds):
        nt.new_session(user_id, passed)
        while _current(user_id):
            data, _ = nt.answer(user_id, _card_id(user_id), _right(user_id), passed)
    return data


def test_next_skill_opens_step_by_step(test_db, monkeypatch):
    """Урок опубликован И предыдущий навык освоен - иначе навык закрыт."""
    _no_sources(monkeypatch)
    _lesson()
    _lesson("اسم وعلامته — часть 1 (Имя и его признаки)")
    assert [s["id"] for s in nt.open_skills("777")] == ["kinds"]
    import random
    random.seed(3)                               # выбор карточек случаен - фиксируем, иначе тест мигает
    for _ in range(40):                          # 40 на ступени 1, затем 40 на ступени 2
        _answer_all("777")
        if nt.skill_mastered("777", "kinds"):
            break
    assert nt.skill_mastered("777", "kinds")
    assert [s["id"] for s in nt.open_skills("777")] == ["kinds", "signs"]
    # «Число» ждёт освоения «Признаков исма», хотя урок уже вышел
    _lesson("الجمع وأنواعه — часть 1")
    assert [s["id"] for s in nt.open_skills("777")] == ["kinds", "signs"]
    # новый навык - не меньше 60% захода, пока не освоен
    w = nt._skill_weights("777", ["kinds", "signs"], 0)
    assert w[1] / sum(w) >= 0.6
    # и старые навыки при нескольких открытых получают повторение
    many = nt._skill_weights("777", ["kinds", "signs", "number"], 3)
    assert all(x > 0 for x in many)


def test_new_skill_is_announced_once(test_db, monkeypatch):
    _no_sources(monkeypatch)
    _lesson()
    _lesson("اسم وعلامته — часть 1")
    told = [_answer_all("777")["finished"].get("new_skill") for _ in range(18)]
    assert told.count("Признаки исма") == 1


def test_group_that_passed_lectures_gets_skills_at_once(test_db, monkeypatch):
    _no_sources(monkeypatch)
    monkeypatch.setattr(nt, "_pool_limit", lambda user_id: nt.corpus().ord["2:141"])
    _lesson()
    g = _group()
    nt.set_group_passed(g["id"], 5)
    assert nt.group_passed(g["id"]) == 5
    got = [s["id"] for s in nt.open_skills("777", passed=5)]
    assert got == ["kinds", "signs", "number", "tense", "bina"]   # уроков по ним ещё нет
    seen = set()
    for _ in range(8):
        nt.new_session("777", 5)
        while _current("777"):
            seen.add(_current("777")["skill"])
            nt.answer("777", _card_id("777"), _right("777"), 5)
    assert seen == set(got)


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
    # устазу открыты все навыки сразу - ему надо видеть, что сдают студенты
    assert api._nahw_passed("555") == len(nt.SKILLS) and api._nahw_passed("777") == 0


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


def test_first_meet_with_case_type_is_flagged_once(test_db, monkeypatch):
    """Первая встреча с типом случая - приложение ждёт «Дальше» и после
    верного ответа; со второй листает само."""
    _no_sources(monkeypatch)
    _lesson()
    seen, flags = set(), []
    for _ in range(3):
        nt.new_session("777")
        while _current("777"):
            ctype = _current("777")["ctype"]
            data, _ = nt.answer("777", _card_id("777"), _right("777"))
            flags.append((ctype in seen, data["feedback"]["first_meet"]))
            seen.add(ctype)
    assert all(met != first for met, first in flags)
