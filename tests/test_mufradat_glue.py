"""Устойчивые сочетания в тренажёре: голова не должна идти без хвоста.

API Quran Academy для связок (предлог+сущ. и т.п.) кладёт перевод ВСЕЙ связки
на первое слово, а следующим ставит "*". В выборке по диапазону страниц это
склеивает _merge_glued_translations, а вот в выборке «Моих слов» по
progress_key склейки не было — и студент получил карточку «مِن — до вас»
вместо «مِن قَبْلِكُمْ — до вас» (07.09.2026, materials/min.jpeg).
"""

import sqlite3

import pytest

import core.mufradat as mufradat
import core.mushaf_words as mushaf_words
from core.sampler import ensure_mufradat_schema


ROWS = [
    # (surah, ayah, position, arabic, translation, progress_key)
    (2, 183, 10, "ٱلَّذِينَ", "которые (были)", 100),
    (2, 183, 11, "مِن", "до вас", 101),          # голова связки
    (2, 183, 12, "قَبْلِكُمْ", "*", 102),          # хвост, своего ключа не имеет
    (2, 183, 13, "لَعَلَّكُمْ", "чтобы вы", 103),
]


@pytest.fixture
def words_db(tmp_path, monkeypatch):
    path = str(tmp_path / "hadiths.db")
    with sqlite3.connect(path) as conn:
        ensure_mufradat_schema(conn)
        conn.executemany(
            "INSERT INTO mufradat_words"
            "(surah_number, ayah_number, position, arabic_text, translation,"
            " language, progress_key) VALUES (?,?,?,?,?,'ru',?)", ROWS)
    monkeypatch.setattr(mufradat, "HADITHS_DB", path)
    monkeypatch.setattr(mushaf_words, "HADITHS_DB", path)
    return path


def test_голова_связки_идёт_с_хвостом(words_db):
    words = mufradat.get_words_by_progress_keys([101])

    assert len(words) == 1
    assert words[0]["arabic_text"] == "مِن قَبْلِكُمْ"
    assert words[0]["translation"] == "до вас"


def test_обычное_слово_не_склеивается(words_db):
    words = mufradat.get_words_by_progress_keys([103])

    assert words[0]["arabic_text"] == "لَعَلَّكُمْ"


def test_хвост_в_пул_не_попадает(words_db):
    """У хвоста свой progress_key есть только в этой фикстуре; на реальных
    данных его нет вовсе. Но даже если ключ попросят напрямую — «*» не слово,
    и _is_junk выбрасывает его из пула."""
    assert mufradat.get_words_by_progress_keys([102]) == []


def test_диапазон_страниц_склеивает_так_же(words_db):
    words = mufradat.get_words_in_range(2, 183, 183)
    glued = [w for w in words if w["translation"] == "до вас"]

    assert glued and glued[0]["arabic_text"] == "مِن قَبْلِكُمْ"
