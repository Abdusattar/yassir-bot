"""Дневная норма тренажёра слов: 40 разных слов И 20 из них верно.

До 15.09.2026 зачёт «Слова» давался за одни 40 проработанных слов - их
можно было набрать, тапая наугад. Теперь второй порог по верным ответам, а
слово, отвеченное сегодня верно, до конца дня больше не спрашивается
(пользователь: «зачем правильные за день выводить по несколько раз»).
"""

import sqlite3

import pytest

import core.mufradat as mufradat


@pytest.fixture
def daily_db(tmp_path, monkeypatch):
    path = str(tmp_path / "hadiths.db")
    monkeypatch.setattr(mufradat, "HADITHS_DB", path)
    monkeypatch.setattr(mufradat, "DAILY_WORDS_FOR_TASK_CREDIT", 4)
    monkeypatch.setattr(mufradat, "DAILY_CORRECT_FOR_TASK_CREDIT", 2)
    return path


def test_сорок_слов_без_верных_не_зачёт(daily_db):
    for key in range(4):
        st = mufradat.record_daily_answered_word("u1", key, correct=False)

    assert st["count"] == 4
    assert st["correct"] == 0
    assert st["done"] is False


def test_зачёт_когда_оба_порога(daily_db):
    mufradat.record_daily_answered_word("u1", 1, correct=True)
    mufradat.record_daily_answered_word("u1", 2, correct=False)
    mufradat.record_daily_answered_word("u1", 3, correct=False)
    st = mufradat.record_daily_answered_word("u1", 4, correct=False)
    assert st["done"] is False, "верных пока одно"

    st = mufradat.record_daily_answered_word("u1", 2, correct=True)

    assert st["count"] == 4, "повтор слова счёт слов не двигает"
    assert st["correct"] == 2
    assert st["done"] is True
    assert mufradat.get_daily_words_status("u1") == st


def test_верное_потом_ошибка_остаётся_взятым(daily_db):
    mufradat.record_daily_answered_word("u1", 7, correct=True)
    st = mufradat.record_daily_answered_word("u1", 7, correct=False)

    assert st["correct"] == 1
    assert mufradat.get_today_correct_keys("u1") == {7}


def test_миграция_добавляет_колонку_correct(daily_db):
    """Таблица со старой схемой (без correct) уже есть на проде."""
    with sqlite3.connect(daily_db) as conn:
        conn.execute(
            "CREATE TABLE mufradat_daily_answered_words("
            "user_id TEXT NOT NULL, date TEXT NOT NULL, word_id INTEGER NOT NULL,"
            " PRIMARY KEY (user_id, date, word_id))")
        conn.execute(
            "INSERT INTO mufradat_daily_answered_words VALUES ('u1', ?, 1)", (mufradat._today(),))

    st = mufradat.record_daily_answered_word("u1", 2, correct=True)

    assert st == {"count": 2, "target": 4, "correct": 1, "correct_target": 2, "done": False}


def _words(n):
    return [
        {"id": i, "progress_key": i, "arabic_text": f"ع{i}", "translation": f"слово{i}",
         "surah_number": 2, "ayah_number": 1}
        for i in range(n)
    ]


def test_сегодняшние_верные_не_спрашиваются():
    words = _words(10)
    taken = {0, 1, 2, 3, 4, 5, 6, 7, 8}

    for _ in range(50):
        picked = mufradat.pick_question_word(words, {}, exclude_keys=taken)
        assert picked["progress_key"] == 9


def test_если_всё_взято_исключение_снимается():
    words = _words(3)

    picked = mufradat.pick_question_word(words, {}, exclude_keys={0, 1, 2})

    assert picked is not None, "лучше повтор, чем тупик «слова закончились»"


def test_generate_question_передаёт_исключение():
    words = _words(12)

    for _ in range(30):
        q = mufradat.generate_question(words, {}, exclude_keys=set(range(11)))
        assert q["word"]["progress_key"] == 11
