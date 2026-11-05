"""Склейка последней строки стр. 1-2 (05.11.2026, Умар устаз).

На стр. 1 («وَلَا ٱلضَّآلِّينَ») и стр. 2 («هُمُ ٱلْمُفْلِحُونَ») переход
предпоследней строки целиком съедает последнюю. Отдельной единицей этапа 1
она не идёт - входит в предыдущую. Листы page*.json не в git: в CI тесты,
которым нужен настоящий лист, пропускаются, гонять локально."""
import os

import pytest

import core.db as db
import core.mushaf_words as mw

HAVE_PAGES = os.path.exists(os.path.join("mushaf_data", "page2.json")) and \
    os.path.exists(os.path.join("mushaf_data", "dm", "page2.json"))
needs_pages = pytest.mark.skipif(not HAVE_PAGES, reason="листов мусхафа нет в git (CI)")


def test_tail_word_count_matches_app_rule():
    w = lambda h: {"type": "word", "html": h}
    end = {"type": "ayah_end", "html": "٥"}
    # «هُمُ» короткое тянет второе, второе на конце аята - тянет дальше, но слов нет
    assert mw._tail_word_count([w("هُمُ"), w("ٱلْمُفْلِحُونَ"), end]) == 2
    # длинное первое слово без конца аята - одно
    assert mw._tail_word_count([w("ٱلَّذِينَ"), w("كَفَرُواْ"), w("سَوَآءٌ")]) == 1
    # потолок три
    assert mw._tail_word_count([w("لَا"), w("رَيْبَ"), end, w("فِيهِ"), end, w("هُدًى")]) == 3


@needs_pages
def test_only_pages_1_and_2_are_absorbed_in_both_layouts():
    for layout, sub in (("madani", ""), ("dm", "dm")):
        found = [p for p in range(1, 605)
                 if os.path.exists(os.path.join("mushaf_data", sub, "page%d.json" % p))
                 and mw.hifz_absorbed_line(p, layout) is not None]
        assert found == [1, 2], (layout, found)
        assert mw.hifz_absorbed_line(1, layout) == 6
        assert mw.hifz_absorbed_line(2, layout) == 5


@needs_pages
def test_step_skips_absorbed_line():
    # стр. 2: 6 строк, вторая половина 3..5; после строки 4 - сразу этап 2
    assert mw.next_hifz_position(2, 3, 1) == (2, 4, 1)
    assert mw.next_hifz_position(2, 4, 1) == (2, 4, 2)
    # указатель, оставшийся на поглощённой строке, тоже уходит на этап 2
    assert mw.next_hifz_position(2, 5, 1) == (2, 5, 2)
    # стр. 1: 7 строк, вторая половина 3..6
    assert mw.next_hifz_position(1, 5, 1) == (1, 5, 2)
    # обычный лист не тронут
    assert mw.next_hifz_position(3, 13, 1) == (3, 14, 1)


@needs_pages
def test_retake_on_absorbed_line_closed_by_merged_unit(test_db):
    db.save_group("-100555001", "N-1", tasks="m,r,t")
    group = db.get_group("-100555001")
    sid = db.add_student("Сатар", group["id"], phone="777001")
    db.save_voice_submission(sid, group["id"], "-100555001", 1, db.get_date(), file_id="f1",
                             hifz_page=2, hifz_line=5, hifz_stage=1)
    sub_id = db.get_student_submissions(sid)[0]["id"]
    db.set_submission_verdict(sub_id, db.VERDICT_RETAKE, "888002")
    assert db.get_open_retakes(sid, group["id"])

    db.save_voice_submission(sid, group["id"], "-100555001", 2, db.get_date(), file_id="f2",
                             hifz_page=2, hifz_line=4, hifz_stage=1)
    assert db.get_open_retakes(sid, group["id"]) == []
