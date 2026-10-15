"""Рейтинг тренажёра слов (28.09.2026, решение пользователя).

Закладку тренажёра студент ставит сам (➖/➕), и в рейтинге она давала
множитель глубины и выбирала дивизион: закладка на стр. 90 при заучивании на
18 поднимала точность 74% на второе место. Кнопки оставлены, а в рейтинг идёт
меньшее из закладки и места заучивания; хафизу - закладка. Не тренировался
дольше 14 дней - не в общем списке, но себя видит.

15.10.2026: и не дальше, чем покрыто словами (covered_page) - хафиз с
закладкой 221 и 180 словами стоял третьим.
"""

import sqlite3
from datetime import date, timedelta

import pytest

import core.mufradat as mufradat
import core.mufradat_bot as mb
import core.mushaf_words as mw
from core.sampler import ensure_mufradat_schema


@pytest.fixture
def lb_db(tmp_path, monkeypatch):
    path = str(tmp_path / "hadiths.db")
    monkeypatch.setattr(mufradat, "HADITHS_DB", path)
    monkeypatch.setattr(mw, "HADITHS_DB", path)
    with sqlite3.connect(path) as conn:
        ensure_mufradat_schema(conn)
        mufradat._ensure_progress_schema(conn)
        conn.execute(mufradat._PAGE_SCHEMA)
        conn.execute(mw._HIFZ_SCHEMA)
        conn.execute(mufradat._DAILY_ANSWERED_SCHEMA)
        # Бакара целиком, по 10 разных слов на аят - 2860 слов: хватает,
        # чтобы покрытие словами доходило до стр. 18-20.
        i = 0
        for ayah in range(1, 287):
            for pos in range(1, 11):
                i += 1
                conn.execute(
                    "INSERT INTO mufradat_words (id, surah_number, ayah_number, position, arabic_text,"
                    " translation, language, progress_key) VALUES (?,2,?,?,'كلمة','слово','ru',?)",
                    (i, ayah, pos, i))
    return path


def _student(path, uid, correct, wrong, words, bookmark, hifz=None, last=None):
    """words разных слов, на каждом поровну верных/неверных."""
    with sqlite3.connect(path) as conn:
        for w in range(1, words + 1):
            conn.execute(
                "INSERT INTO mufradat_progress (user_id, word_id, correct_streak, wrong_count,"
                " days_correct, correct_count) VALUES (?,?,0,?,0,?)",
                (uid, w, wrong // words, correct // words))
        conn.execute("INSERT INTO mufradat_page (user_id, page_number, start_ayah, end_ayah)"
                     " VALUES (?,?,0,0)", (uid, bookmark))
        if hifz:
            conn.execute("INSERT INTO mushaf_hifz_pointer (user_id, page_number, line_index, stage,"
                         " updated_at) VALUES (?,?,0,1,'x')", (uid, hifz))
        if last:
            conn.execute("INSERT INTO mufradat_daily_answered_words (user_id, date, word_id)"
                         " VALUES (?,?,1)", (uid, last))


@pytest.mark.parametrize("bookmark, hifz, hafiz, covered, want", [
    (90, 18, False, None, 18),     # закладка впереди - в зачёт место заучивания
    (5, 25, False, None, 5),       # закладка отстала - маленький пул, в зачёт закладка
    (52, 52, False, None, 52),
    (31, None, False, None, 31),   # места заучивания нет - как раньше
    (10, 40, True, None, 10),      # хафиз - закладка
    (90, 18, True, None, 90),
    (221, 604, True, 3, 3),        # хафиз, 180 слов: глубже покрытого не идёт
    (52, 52, False, 47, 47),       # покрыто чуть меньше места - в зачёт покрытое
    (18, 18, False, 40, 18),       # покрыто с запасом - ничего не меняется
])
def test_rating_depth(bookmark, hifz, hafiz, covered, want):
    assert mufradat.rating_depth(bookmark, hifz, hafiz, covered) == want


def test_covered_page():
    sizes = {1: 29, 2: 60, 3: 139, 4: 200}
    assert mufradat.covered_page(0, sizes) == 1
    assert mufradat.covered_page(29, sizes) == 1
    assert mufradat.covered_page(30, sizes) == 2
    assert mufradat.covered_page(180, sizes) == 4
    assert mufradat.covered_page(5000, sizes) == 4   # открыл больше пула - вся глубина


def test_bookmark_ahead_no_longer_lifts_rank(lb_db):
    """Живой случай: 74% с закладкой 90 при заучивании 18 обгоняла 95% на 18."""
    _student(lb_db, "far", correct=3 * 1400, wrong=1400, words=1400, bookmark=90, hifz=18)
    _student(lb_db, "honest", correct=19 * 1400, wrong=1400, words=1400, bookmark=18, hifz=18)
    board = mufradat.get_leaderboard()
    assert [uid for uid, _ in board] == ["honest", "far"]
    far = dict(board)["far"]
    assert far["page"] == 18 and far["bookmark"] == 90 and far["hifz_page"] == 18


def test_hafiz_bookmark_capped_by_coverage(lb_db):
    """Хафизу - закладка, но не глубже покрытого словами."""
    _student(lb_db, "h", correct=9 * 1400, wrong=1400, words=1400, bookmark=90, hifz=18)
    covered = mufradat.covered_page(1400, mufradat._pool_sizes("ru"))
    assert 18 < covered < 90
    assert dict(mufradat.get_leaderboard(hafiz={"h"}))["h"]["page"] == covered


def test_few_words_deep_bookmark_below_volume(lb_db):
    """Живой случай 15.10.2026: хафиз, закладка 221, 180 слов, 97,8% - был
    третьим, выше студентов с тысячами слов на своей глубине."""
    _student(lb_db, "hafiz", correct=44 * 180, wrong=180, words=180, bookmark=221, hifz=604)
    _student(lb_db, "worker", correct=19 * 1400, wrong=1400, words=1400, bookmark=19, hifz=19)
    board = mufradat.get_leaderboard(hafiz={"hafiz"})
    assert [uid for uid, _ in board] == ["worker", "hafiz"]
    assert dict(board)["hafiz"]["page"] < 5


def test_last_date_in_score(lb_db):
    _student(lb_db, "a", correct=100, wrong=0, words=100, bookmark=10, last="2026-09-20")
    assert dict(mufradat.get_leaderboard())["a"]["last_date"] == "2026-09-20"


def test_idle_days_hide_from_public_list(lb_db, monkeypatch):
    today = date(2026, 9, 28)
    monkeypatch.setattr(mb, "get_date", lambda: today.isoformat())
    monkeypatch.setattr(mb, "hafiz_phones", lambda: set())
    monkeypatch.setattr(mb, "find_user_by_phone", lambda uid: {"phone": uid})
    monkeypatch.setattr(mb, "get_learning_group", lambda uid: {"id": 1})
    _student(lb_db, "fresh", correct=900, wrong=100, words=100, bookmark=20, hifz=20,
             last=(today - timedelta(days=14)).isoformat())
    _student(lb_db, "idle", correct=950, wrong=50, words=100, bookmark=30, hifz=30,
             last=(today - timedelta(days=15)).isoformat())
    _student(lb_db, "never", correct=950, wrong=50, words=100, bookmark=30, hifz=30)
    public = [uid for uid, _ in mb._group_leaderboard_for_this_bot()]
    assert public == ["fresh"]
    # Себя человек видит всегда: полный список его сохраняет.
    assert {uid for uid, _ in mb._leaderboard_for_this_bot()} == {"fresh", "idle", "never"}


def _score(page, acc=90.0, last="2026-09-27"):
    return {"accuracy": acc, "correct": 90, "wrong": 10, "n": 100, "attempted": 50,
            "page": page, "last_date": last, "_sort_key": 1.0, "wilson": 0.8}


def _api_board(monkeypatch, me_id, full, public):
    import asyncio
    import core.mufradat_api as api
    from aiohttp.test_utils import TestClient, TestServer
    monkeypatch.setattr(api, "validate_init_data", lambda raw, token: {"id": raw})
    monkeypatch.setattr(api, "_leaderboard_for_this_bot", lambda: full)
    monkeypatch.setattr(api, "_group_leaderboard_for_this_bot", lambda: public)
    monkeypatch.setattr(api, "get_learning_group", lambda uid: {"id": 1})
    monkeypatch.setattr(api, "_display_name", lambda uid: "Имя " + uid)
    monkeypatch.setattr(api, "_group_name", lambda uid: "Группа 3")
    monkeypatch.setattr(mb, "get_date", lambda: "2026-09-28")

    async def run():
        client = TestClient(TestServer(api.build_app()))
        await client.start_server()
        try:
            resp = await client.get("/api/muf/leaderboard", headers={"X-Telegram-Init-Data": me_id})
            return await resp.json()
        finally:
            await client.close()
    return asyncio.run(run())


def test_api_me_row_below_top_seven(test_db, monkeypatch):
    """9-е место: в списке приложение рисует семёрку, себя - отдельной строкой."""
    full = [(str(i), _score(20)) for i in range(1, 11)]
    d = _api_board(monkeypatch, "9", full, full)
    me = d["me"]
    assert (me["place"], me["total"], me["division_no"], me["hidden"]) == (9, 10, 1, False)
    assert me["accuracy"] == 90.0 and me["page"] == 20 and me["name"] == "Имя 9"
    assert "last_date" not in d["divisions"][0]["entries"][0]   # служебное не уходит


def test_api_me_hidden_when_idle(test_db, monkeypatch):
    full = [("1", _score(20)), ("2", _score(20, last="2026-09-09"))]
    d = _api_board(monkeypatch, "2", full, full[:1])
    assert d["me"]["hidden"] is True and d["me"]["idle_days"] == 19
    assert "place" not in d["me"]
