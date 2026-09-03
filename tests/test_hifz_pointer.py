"""Автомат движения указателя 40+40.

Он ЗАДУБЛИРОВАН: тот же порядок шагов живёт на фронтенде (hifzNext в
mushaf_data/index.html), потому что в приложении переход должен произойти
мгновенно, а сдача голосом в группе идёт вообще мимо приложения. Эти тесты
фиксируют формулу, по которой обе стороны обязаны совпадать - в первую
очередь границу половины листа (line < n//2), из-за которой уже был
рассинхрон между JS и Python в подписи сдачи.
"""
import json
import os
import sqlite3

import core.mushaf_words as mw


def test_stage1_walks_lines_inside_first_half():
    # 15 строк: первая половина 0..6, вторая 7..14 (mid = 7)
    assert mw.next_hifz_position(5, 0, 1, 15) == (5, 1, 1)
    assert mw.next_hifz_position(5, 5, 1, 15) == (5, 6, 1)


def test_stage1_end_of_half_switches_to_stage2():
    assert mw.next_hifz_position(5, 6, 1, 15) == (5, 6, 2)    # конец первой половины
    assert mw.next_hifz_position(5, 14, 1, 15) == (5, 14, 2)  # конец второй


def test_stage2_first_half_returns_to_lines_of_second_half():
    assert mw.next_hifz_position(5, 6, 2, 15) == (5, 7, 1)


def test_stage2_second_half_opens_whole_page():
    assert mw.next_hifz_position(5, 14, 2, 15) == (5, 14, 3)


def test_stage3_moves_to_next_page_from_first_line():
    assert mw.next_hifz_position(5, 14, 3, 15) == (6, 0, 1)


def test_last_page_does_not_run_off_the_mushaf():
    assert mw.next_hifz_position(604, 14, 3, 15) == (604, 14, 3)


def test_half_boundary_follows_line_count_not_hardcoded_8():
    """Страница с названием суры короче: 13 строк -> mid = 6, а не 7.
    Если бы граница была захардкожена, вторая половина съехала бы."""
    assert mw.next_hifz_position(1, 5, 1, 13) == (1, 5, 2)   # 0..5 - вся первая половина
    assert mw.next_hifz_position(1, 5, 2, 13) == (1, 6, 1)   # вторая начинается с 6
    # На 15 строках та же строка 5 - ещё середина первой половины, не конец.
    assert mw.next_hifz_position(1, 5, 1, 15) == (1, 6, 1)


def test_advance_pointer_noop_for_student_without_pointer(test_hadiths_db):
    assert mw.advance_hifz_pointer("no_such_user") is None


def test_advance_pointer_moves_and_persists(test_hadiths_db):
    import os

    mw.set_hifz_pointer("u1", 5, 0, 1)
    # Заодно доказываем, что писали во ВРЕМЕННУЮ базу, а не в настоящую
    # sources/hadiths.db (у разработчика она существует и молча приняла бы
    # запись - именно так тест и проходил локально, роняя CI).
    assert os.path.exists(test_hadiths_db)

    assert mw.advance_hifz_pointer("u1") == {"page": 5, "line": 1, "stage": 1}
    assert mw.get_hifz_pointer("u1") == {"page": 5, "line": 1, "stage": 1}


def test_page_text_line_count_reads_real_page_data():
    """Реальные данные мусхафа: строка названия суры и басмала не должны
    попадать в счёт, иначе половина листа съедет."""
    assert mw.page_text_line_count(5) == 15


# ── Счётчик прогресса 40+40 (03.09.2026) ────────────────────────────────
# Частичные сдачи по этапам 2/3 (половина/страница) растягиваются на
# 2-3 дня - число одно (0-80), дельта прибавляется, не заменяет.

def test_hifz_progress_starts_at_zero(test_hadiths_db):
    assert mw.get_hifz_progress("u1", 5, 2, 0) == 0


def test_hifz_progress_accumulates_deltas(test_hadiths_db):
    assert mw.add_hifz_progress("u1", 5, 2, 0, 15) == 15
    assert mw.add_hifz_progress("u1", 5, 2, 0, 20) == 35
    assert mw.get_hifz_progress("u1", 5, 2, 0) == 35


def test_hifz_progress_clamps_at_target(test_hadiths_db):
    mw.add_hifz_progress("u1", 5, 3, 0, 70)
    assert mw.add_hifz_progress("u1", 5, 3, 0, 40) == mw.HIFZ_PROGRESS_TARGET


def test_hifz_progress_units_are_independent(test_hadiths_db):
    """Половина листа, страница целиком и разные половины (0/1) - разные
    единицы, счётчик одной не должен утекать в другую."""
    mw.add_hifz_progress("u1", 5, 2, 0, 10)
    mw.add_hifz_progress("u1", 5, 2, 1, 25)
    mw.add_hifz_progress("u1", 5, 3, 0, 5)
    assert mw.get_hifz_progress("u1", 5, 2, 0) == 10
    assert mw.get_hifz_progress("u1", 5, 2, 1) == 25
    assert mw.get_hifz_progress("u1", 5, 3, 0) == 5


def test_hifz_progress_ignores_negative_delta(test_hadiths_db):
    mw.add_hifz_progress("u1", 5, 2, 0, 30)
    assert mw.add_hifz_progress("u1", 5, 2, 0, -100) == 30


# ── "Новые" слова в "Мои слова" (03.09.2026) ────────────────────────────

def _seed_mufradat_words(db_path, rows):
    """rows: (surah, ayah, position, progress_key, arabic_text, translation)."""
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mufradat_words(
            surah_number INTEGER, ayah_number INTEGER, position INTEGER,
            language TEXT, progress_key INTEGER, arabic_text TEXT, translation TEXT
        )
    """)
    conn.executemany(
        "INSERT INTO mufradat_words (surah_number, ayah_number, position, language, "
        "progress_key, arabic_text, translation) VALUES (?,?,?,'ru',?,?,?)",
        rows
    )
    conn.commit()
    conn.close()


def _write_page_json(pages_dir, page_number, line_number, triples):
    """mushaf_data/*.json сгенерированы (scripts/export_mushaf_page.py) и
    намеренно НЕ в git (.gitignore) - на CI-раннере их нет вообще, поэтому
    тесты, трогающие _line_word_triples, пишут свой минимальный файл в
    monkeypatch-нутый _MUSHAF_DATA_DIR, а не читают настоящие данные."""
    data = {"lines": [{
        "line": line_number, "type": "text",
        "tokens": [
            {"type": "word", "surah": s, "ayah": a, "position": p}
            for s, a, p in triples
        ],
    }]}
    with open(os.path.join(pages_dir, f"page{page_number}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f)


def test_hifz_start_page_set_once(test_hadiths_db):
    assert mw.get_or_init_hifz_start_page("u1", 15) == 15
    # Повторный вызов с другой страницей не должен перезаписать - это
    # ИСТОРИЧЕСКИЙ факт "откуда начал", а не текущий указатель.
    assert mw.get_or_init_hifz_start_page("u1", 20) == 15


def test_check_new_words_adds_words_from_start_page(test_hadiths_db, tmp_path, monkeypatch):
    # (surah, ayah, position) - условная страница 2, одна текстовая строка.
    monkeypatch.setattr(mw, "_MUSHAF_DATA_DIR", str(tmp_path))
    mw._first_occurrence_cache = None  # изолируем от кэша прошлых тестов
    triples = [(2, 1, 1), (2, 2, 1), (2, 2, 2), (2, 2, 3), (2, 2, 4), (2, 2, 5), (2, 2, 6)]
    _write_page_json(str(tmp_path), 2, 3, triples)  # line_index=2 -> json "line":3
    _seed_mufradat_words(test_hadiths_db, [
        (2, 1, 1, 201, "الٓمٓ", "Алиф лам мим"),
        (2, 2, 1, 202, "ذَٰلِكَ", "Это"),
        (2, 2, 2, 203, "ٱلْكِتَـٰبُ", "Писание"),
        (2, 2, 3, 204, "لَا", "нет"),
        (2, 2, 4, 205, "رَيْبَ", "сомнения"),
        (2, 2, 5, 206, "فِيهِ", "в нём"),
        (2, 2, 6, 207, "هُدًى", "руководство"),
    ])
    mw.get_or_init_hifz_start_page("u1", 2)
    mw.check_new_words_for_line("u1", 2, 2)
    words = mw.list_starred_words("u1")
    assert len(words) == 7
    assert all(w["source"] == "hifz_new" and w["is_new"] for w in words)


def test_check_new_words_skips_before_start_page(test_hadiths_db, tmp_path, monkeypatch):
    monkeypatch.setattr(mw, "_MUSHAF_DATA_DIR", str(tmp_path))
    mw._first_occurrence_cache = None
    _write_page_json(str(tmp_path), 2, 3, [(2, 1, 1)])
    _seed_mufradat_words(test_hadiths_db, [
        (2, 1, 1, 201, "الٓمٓ", "Алиф лам мим"),
    ])
    mw.get_or_init_hifz_start_page("u1", 5)  # старт - стр. 5, стр. 2 уже позади
    mw.check_new_words_for_line("u1", 2, 2)
    assert mw.list_starred_words("u1") == []


def test_check_new_words_article_and_diacritics_do_not_make_it_new(test_hadiths_db, tmp_path, monkeypatch):
    """03.09.2026, решение пользователя: ٱلْكِتَـٰبُ ("Писание", условно стр. 2)
    и كِتَـٰبَ ("Писание", условно стр. 15) - одно и то же слово для студента
    (как английские the/a), артикль и огласовки не в счёт - только сама
    первая встреченная пара (костяк+перевод) считается новой."""
    monkeypatch.setattr(mw, "_MUSHAF_DATA_DIR", str(tmp_path))
    mw._first_occurrence_cache = None
    _write_page_json(str(tmp_path), 2, 3, [(2, 2, 2)])
    _write_page_json(str(tmp_path), 15, 15, [(2, 101, 16)])
    _seed_mufradat_words(test_hadiths_db, [
        (2, 2, 2, 203, "ٱلْكِتَـٰبُ", "Писание"),
        (2, 101, 16, 1681, "كِتَـٰبَ", "Писание"),
    ])
    mw.get_or_init_hifz_start_page("u1", 2)
    mw.check_new_words_for_line("u1", 2, 2)    # стр. 2, line_index=2 ("line":3)
    mw.check_new_words_for_line("u1", 15, 14)  # стр. 15, line_index=14 ("line":15)
    words = mw.list_starred_words("u1")
    assert len(words) == 1
    assert words[0]["surah"] == 2 and words[0]["ayah"] == 2  # только вхождение со стр. 2


def test_check_new_words_different_translation_is_still_new(test_hadiths_db, tmp_path, monkeypatch):
    """А вот если перевод другой - это уже другое слово (решение
    пользователя), даже если костяк букв совпадает."""
    monkeypatch.setattr(mw, "_MUSHAF_DATA_DIR", str(tmp_path))
    mw._first_occurrence_cache = None
    _write_page_json(str(tmp_path), 2, 3, [(2, 2, 2)])
    _write_page_json(str(tmp_path), 15, 15, [(2, 101, 16)])
    _seed_mufradat_words(test_hadiths_db, [
        (2, 2, 2, 203, "ٱلْكِتَـٰبُ", "Писание"),
        (2, 101, 16, 1681, "كِتَـٰبَ", "предписал"),  # тот же костяк, другой смысл
    ])
    mw.get_or_init_hifz_start_page("u1", 2)
    mw.check_new_words_for_line("u1", 2, 2)
    mw.check_new_words_for_line("u1", 15, 14)
    words = mw.list_starred_words("u1")
    assert len(words) == 2
