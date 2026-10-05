"""Выученное слово не обнуляется, если его не было в «Моих словах» (05.10.2026).

С 28.08 remove_starred_by_progress_key сбрасывала correct_streak у ЛЮБОГО слова
на пороге MASTERY_STREAK: выученных не оставалось ни у кого, «Общий вес» падал
от верных ответов (жалоба Толкун). Сброс задуман только для выхода из «Моих слов».
"""
import sqlite3

import pytest

import core.mufradat as mufradat
import core.mushaf_words as mw


@pytest.fixture
def db(test_hadiths_db, monkeypatch):
    monkeypatch.setattr(mufradat, "HADITHS_DB", test_hadiths_db)
    return test_hadiths_db


def _streak(uid, key):
    return mufradat.get_progress_map(uid, [key])[key]["correct_streak"]


def test_выученное_обычное_слово_остаётся_выученным(db):
    for _ in range(mufradat.MASTERY_STREAK):
        mufradat.record_answer("u1", 101, True)

    assert _streak("u1", 101) == mufradat.MASTERY_STREAK
    assert mufradat.is_mastered(mufradat.get_progress_map("u1", [101])[101])


def test_слово_из_моих_слов_по_выходу_начинает_заново(db):
    with sqlite3.connect(db) as c:
        mw._ensure_schema(c)
        c.execute("INSERT INTO mushaf_starred_words(user_id, surah, ayah, position, arabic_html, translation, added_at, progress_key) VALUES ('u1', 2, 2, 1, 'x', 'y', '2026-10-05', 202)")
    assert 202 in mw.get_starred_progress_keys("u1")
    for _ in range(mufradat.MASTERY_STREAK):
        mufradat.record_answer("u1", 202, True)

    assert 202 not in mw.get_starred_progress_keys("u1")
    assert _streak("u1", 202) == 0
