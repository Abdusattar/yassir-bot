"""Раскладка «Дар аль-Маариф (египетский)» - второй вариант мусхафа (23.09.2026).

Проверяем то, на чём стоит заучивание: данные dm/ собраны верно, указатель
40+40 считает строки своей раскладки, при смене раскладки место переезжает
на ту же строку, а сравнение студентов идёт по мединским страницам.
"""
import json
import os

import pytest

from core import mushaf_words as mw
from core.mufradat_bot import _hifz_place

DM = os.path.join(os.path.dirname(__file__), "..", "mushaf_data", "dm")
# Мединские листы (mushaf_data/page*.json) в git не лежат - в раннере их нет,
# а dm/ лежит. Тесты, которым нужны оба, в CI пропускаются.
needs_madani = pytest.mark.skipif(
    not os.path.exists(os.path.join(os.path.dirname(__file__), "..", "mushaf_data", "page586.json")),
    reason="нет мединских page*.json (они не в git)")


def _dm(page):
    with open(os.path.join(DM, "page%d.json" % page), encoding="utf-8") as f:
        return json.load(f)


def _text_lines(data):
    return [l for l in data["lines"] if l["type"] == "text"]


def test_dm_pages_match_the_book_samples():
    # Сверено с печатной книгой (PDF Дар аль-Маарифа): стр. 300, строка 6
    # кончается на «ومن» (18:57:1), стр. 600 начинается с 100:10.
    line6 = _text_lines(_dm(300))[5]["tokens"]
    words = [t for t in line6 if t["type"] == "word"]
    assert (words[0]["surah"], words[0]["ayah"], words[0]["position"]) == (18, 56, 11)
    assert (words[-1]["surah"], words[-1]["ayah"], words[-1]["position"]) == (18, 57, 1)
    first = [t for t in _text_lines(_dm(600))[0]["tokens"] if t["type"] == "word"][0]
    assert (first["surah"], first["ayah"]) == (100, 10)


def test_dm_every_word_once_in_order():
    seen = []
    for p in range(1, 605):
        for l in _text_lines(_dm(p)):
            seen.extend((t["surah"], t["ayah"], t["position"]) for t in l["tokens"] if t["type"] == "word")
    assert len(seen) == len(set(seen)) == 77433
    assert seen == sorted(seen)


def test_foreign_glyph_carries_its_font_page():
    # Слово с другого мединского листа несёт fp - номер листа его шрифта.
    data = _dm(599)
    fps = {t.get("fp") for l in _text_lines(data) for t in l["tokens"]}
    fps.discard(None)
    assert fps and all(fp != data["font_page"] for fp in fps)


@needs_madani
def test_layout_default_and_switch_moves_pointer(test_hadiths_db):
    uid = "5550001"
    assert mw.get_mushaf_layout(uid) == "madani"
    # Мединская стр. 600 строка 5 начинается с 100:6 (у 1405 это ещё стр. 599).
    mw.set_hifz_pointer(uid, 600, 0, 1)
    first = mw._line_word_triples(600, 0)[0]
    ptr = mw.set_mushaf_layout(uid, "dm")
    assert ptr["layout"] == "dm"
    assert mw.word_place("dm", first) == (ptr["page"], ptr["line"])
    assert ptr["stage"] == 1
    # Сравнение студентов - по мединскому листу первого слова строки.
    dm_first = mw._line_word_triples(ptr["page"], ptr["line"], "dm")[0]
    assert ptr["madani_page"] == mw.word_place("madani", dm_first)[0]
    # И обратно - на ту же строку.
    back = mw.set_mushaf_layout(uid, "madani")
    assert (back["page"], back["line"], back["stage"]) == (600, 0, 1)


@needs_madani
def test_switch_keeps_stage_and_goes_to_half_start(test_hadiths_db):
    uid = "5550002"
    mw.set_hifz_pointer(uid, 300, 10, 2)      # вторая половина, этап 2
    ptr = mw.set_mushaf_layout(uid, "dm")
    n = mw.page_text_line_count(ptr["page"], layout="dm")
    assert ptr["stage"] == 2 and ptr["line"] in (0, n // 2)


@needs_madani
def test_switch_carries_the_4040_counter(test_hadiths_db):
    uid = "5550004"
    mw.set_hifz_pointer(uid, 300, 0, 3)
    mw.set_hifz_progress(uid, 300, 3, 0, 60)
    ptr = mw.set_mushaf_layout(uid, "dm")
    assert mw.get_hifz_progress(uid, ptr["page"], 3, 0) == 60


def test_old_madani_submission_does_not_close_dm_line(test_db):
    from core.db import save_voice_submission, has_submission_for_unit
    save_voice_submission(1, 1, -100, 55, "2026-09-23", hifz_page=300, hifz_line=5, hifz_stage=1)
    assert has_submission_for_unit(1, 1, 300, 5, 1)
    assert not has_submission_for_unit(1, 1, 300, 5, 1, "dm")
    save_voice_submission(1, 1, -100, 56, "2026-09-23", hifz_page=300, hifz_line=5, hifz_stage=1,
                          hifz_layout="dm")
    assert has_submission_for_unit(1, 1, 300, 5, 1, "dm")


@needs_madani
def test_next_position_uses_layout_line_count(test_hadiths_db):
    # Стр. 586 в 1405: 12 текстовых строк (заголовки двух сур), у нас - 13.
    assert mw.page_text_line_count(586, layout="dm") == 12
    assert mw.page_text_line_count(586) == 13
    assert mw.next_hifz_position(586, 11, 1, layout="dm") == (586, 11, 2)   # последняя строка листа
    assert mw.next_hifz_position(586, 11, 1) == (586, 12, 1)


def test_place_names_the_book():
    assert _hifz_place(12, 3, 1, layout="dm") == "стр. 12 (египетский), строка 4"
    assert _hifz_place(12, 3, 1) == "стр. 12, строка 4"


@pytest.mark.parametrize("bad", ["", "indopak", None])
def test_bad_layout_rejected(test_hadiths_db, bad):
    with pytest.raises(ValueError):
        mw.set_mushaf_layout("5550003", bad)


def test_empty_filler_lines_not_counted_dm():
    """Стр. 1 и 2: после настоящих 7 и 6 строк в данных идут 7 пустых "text".
    С ними стр. 2 считалась за 13 строк, и после 6 настоящих место уходило на
    несуществующую строку 7 (случай Таласа, 23.09.2026)."""
    assert mw.page_text_line_count(1, layout="dm") == 7
    assert mw.page_text_line_count(2, layout="dm") == 6
    # стр. 2 - 3+3: после третьей строки этап 2 первой половины
    assert mw.next_hifz_position(2, 2, 1, layout="dm") == (2, 2, 2)
    assert mw.next_hifz_position(2, 5, 2, layout="dm") == (2, 5, 3)


@needs_madani
def test_empty_filler_lines_not_counted_madani():
    assert mw.page_text_line_count(1) == 7
    assert mw.page_text_line_count(2) == 6
    assert mw.next_hifz_position(2, 2, 1) == (2, 2, 2)
