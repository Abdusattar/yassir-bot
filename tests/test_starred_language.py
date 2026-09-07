"""«Мои слова»: перевод всегда из словаря, а не из того, что видел студент.

Живой баг 07.09.2026: в списке оказалось узбекское «куфр келтиради» на слове
يَكْفُرُ (2:99) — страница чтения присылала тот перевод, который показывала, а
студент читал с переключённым языком. Снимок в таблице обязан быть на одном
языке: на остальные список переводится при показе.
"""

import sqlite3

import pytest

import core.mushaf_words as mw
from core.sampler import ensure_mufradat_schema


WORDS = [
    (2, 99, 7, "يَكْفُرُ", "проявляет неверие (никто)", "ru", 7755),
    (2, 99, 7, "يَكْفُرُ", "куфр келтиради", "uz", 7755),
    (2, 99, 8, "بِهَآ", "в них,", "ru", 7756),
]


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = str(tmp_path / "hadiths.db")
    with sqlite3.connect(path) as conn:
        ensure_mufradat_schema(conn)
        conn.executemany(
            "INSERT INTO mufradat_words"
            "(surah_number, ayah_number, position, arabic_text, translation,"
            " language, progress_key) VALUES (?,?,?,?,?,?,?)", WORDS)
    monkeypatch.setattr(mw, "HADITHS_DB", path)
    return path


def test_чужой_язык_со_страницы_не_попадает_в_список(db):
    mw.add_starred_word(1, 2, 99, 7, "يَكْفُرُ", "куфр келтиради")

    words = mw.list_starred_words(1)

    assert words[0]["translation"] == "проявляет неверие (никто)"


def test_уже_лежащая_строка_чинится_при_показе(db):
    """Строки, добавленные до правки, переписывать не надо — список берёт
    перевод из словаря на каждый показ."""
    with sqlite3.connect(db) as conn:
        mw._ensure_schema(conn)
        conn.execute(
            "INSERT INTO mushaf_starred_words"
            "(user_id, surah, ayah, position, arabic_html, translation,"
            " added_at, progress_key, source) VALUES (1,2,99,7,?,?,?,7755,'reading')",
            ("يَكْفُرُ", "куфр келтиради", "2026-09-01T10:00:00+00:00"))

    words = mw.list_starred_words(1)

    assert words[0]["translation"] == "проявляет неверие (никто)"


def test_на_своём_языке_список_переводится(db):
    mw.add_starred_word(1, 2, 99, 7, "يَكْفُرُ", "проявляет неверие (никто)")

    words = mw.list_starred_words(1, language="uz")

    assert words[0]["translation"] == "куфр келтиради"


def test_нет_строки_в_словаре_остаётся_присланное(db):
    """Слова нет в mufradat_words — пустая строка в списке была бы хуже."""
    mw.add_starred_word(1, 2, 99, 99, "كلمة", "перевод со страницы")

    words = mw.list_starred_words(1)

    assert words[0]["translation"] == "перевод со страницы"
