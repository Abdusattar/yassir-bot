"""Место догоняет себя, когда стена пересдачи отпустила (20.09.2026).

Случай пользователя 19.09: на стр. 16 он закрыл четыре пересдачи первого
этапа, и место осталось на ПОСЛЕДНЕЙ СТРОКЕ первой половины вместо перехода
на саму первую половину (этап 2). Ставил руками через «поправить» и с
первого раза попал во вторую половину.

Причина не в пересдачах, а в том, что шаг вперёд делает приложение сразу
после сдачи: пока висел долг, стена (13.09.2026) не пускала место через
границу этапа, шаг не состоялся - и после закрытия долга вперёд студента
никто не двигал. Замер на проде 20.09: так стояли 12 человек, восьмерым
уже ничто не мешало, самый старый случай с 09.09.
"""
import asyncio

import pytest

import core.db as db
import core.mushaf_words as mw
import core.mufradat_api as api

pytestmark = pytest.mark.usefixtures("test_hadiths_db")

CHAT = "-100555001"
PHONE = "555001"
PAGE = 16          # 15 текстовых строк: первая половина 0..6, вторая 7..14


@pytest.fixture
def student(test_db, monkeypatch):
    # Число строк листа берём фиксированным: в тестах mushaf_data может не
    # быть, а формула границы (n // 2) проверена в test_hifz_pointer.
    monkeypatch.setattr(mw, "page_text_line_count", lambda page, *a, **k: 15)
    monkeypatch.setattr(api, "page_text_line_count", lambda page, *a, **k: 15)
    db.save_group(CHAT, "N-1", tasks="m,r,t")
    db.update_group_type(CHAT, "pro")
    group = db.get_group(CHAT)
    db.add_student("Сатар", group["id"], phone=PHONE)
    return {"group": group, "student": db.find_by_phone(PHONE, group["id"])}


def _submit(student, page, line, stage, message_id):
    db.save_voice_submission(student["student"]["id"], student["group"]["id"], CHAT,
                             message_id, "2026-09-19", file_id="f%s" % message_id,
                             hifz_page=page, hifz_line=line, hifz_stage=stage)
    with db.db() as c:
        return c.execute("SELECT id FROM voice_submissions WHERE message_id=?",
                         (message_id,)).fetchone()["id"]


def _pointer():
    p = mw.get_hifz_pointer(PHONE)
    return (p["page"], p["line"], p["stage"]) if p else None


def _catch_up():
    return api._hifz_catch_up(PHONE)


# ── Ради чего всё: место догоняет, когда долгов не осталось ─────────────────

def test_pointer_catches_up_over_the_stage_boundary(student):
    """Ровно случай пользователя: последняя строка первой половины сдана,
    долгов нет - место обязано стоять на первой половине (этап 2)."""
    mw.set_hifz_pointer(PHONE, PAGE, 6, 1)
    _submit(student, PAGE, 6, 1, 101)

    _catch_up()

    assert _pointer() == (PAGE, 6, 2)


def test_catch_up_waits_while_a_debt_is_open(student):
    """Долг есть - стена стоит, место не трогаем: иначе спорили бы с ней."""
    mw.set_hifz_pointer(PHONE, PAGE, 6, 1)
    sub = _submit(student, PAGE, 6, 1, 102)
    debt = _submit(student, PAGE, 2, 1, 103)
    db.set_submission_verdict(debt, db.VERDICT_RETAKE, "ustaz")

    _catch_up()

    assert _pointer() == (PAGE, 6, 1)


def test_catch_up_runs_as_soon_as_the_debt_is_closed(student):
    """Пересдал - и на ближайшем входе в приложение место уже впереди."""
    mw.set_hifz_pointer(PHONE, PAGE, 6, 1)
    _submit(student, PAGE, 6, 1, 104)
    debt = _submit(student, PAGE, 2, 1, 105)
    db.set_submission_verdict(debt, db.VERDICT_RETAKE, "ustaz")
    _catch_up()
    assert _pointer() == (PAGE, 6, 1)

    _submit(student, PAGE, 2, 1, 106)          # пересдача той же единицы

    _catch_up()

    assert _pointer() == (PAGE, 6, 2)


def test_catch_up_walks_several_closed_units_at_once(student):
    """Не по шагу за заход: если закрыто несколько единиц подряд, доходим
    до настоящей работы сразу."""
    mw.set_hifz_pointer(PHONE, PAGE, 4, 1)
    for i, line in enumerate((4, 5, 6)):
        _submit(student, PAGE, line, 1, 110 + i)

    _catch_up()

    assert _pointer() == (PAGE, 6, 2)          # этап 2 ещё не начат - тут и встали


def test_catch_up_does_not_move_from_real_work(student):
    """Единица не закрыта - место не двигается."""
    mw.set_hifz_pointer(PHONE, PAGE, 3, 1)

    _catch_up()

    assert _pointer() == (PAGE, 3, 1)


def test_catch_up_on_stage2_needs_the_counter_not_a_submission(student):
    """На этапах 2/3 единицу закрывает счётчик 40+40, а не сдача: одна
    запись в середине работы двигать место не должна."""
    mw.set_hifz_pointer(PHONE, PAGE, 0, 2)
    _submit(student, PAGE, 0, 2, 120)
    _catch_up()
    assert _pointer() == (PAGE, 0, 2)

    mw.add_hifz_progress(PHONE, PAGE, 2, 0, mw.HIFZ_PROGRESS_TARGET)

    _catch_up()

    assert _pointer() == (PAGE, 7, 1)          # первая половина закрыта - строки второй


def test_catch_up_is_noop_without_pointer_or_group(test_db, monkeypatch):
    monkeypatch.setattr(api, "page_text_line_count", lambda page, *a, **k: 15)
    assert api._hifz_catch_up("no_such_user") is None


def test_catch_up_stops_at_the_end_of_the_mushaf(student):
    """Последняя страница: шагать некуда, цикл обязан остановиться."""
    mw.set_hifz_pointer(PHONE, 604, 14, 3)
    mw.add_hifz_progress(PHONE, 604, 3, 0, mw.HIFZ_PROGRESS_TARGET)

    _catch_up()

    assert _pointer() == (604, 14, 3)


# ── Стена как была: «done» для неё считается той же меркой ──────────────────

def test_wall_still_sees_a_finished_unit_as_closed_move(student):
    mw.set_hifz_pointer(PHONE, PAGE, 6, 1)
    _submit(student, PAGE, 6, 1, 130)
    debt = _submit(student, PAGE, 2, 1, 131)
    db.set_submission_verdict(debt, db.VERDICT_RETAKE, "ustaz")

    data = api._hifz_retakes(PHONE)

    assert data["done"] is True and len(data["retakes"]) == 1


def test_wall_is_not_raised_when_there_is_still_work_here(student):
    mw.set_hifz_pointer(PHONE, PAGE, 3, 1)
    debt = _submit(student, PAGE, 2, 1, 132)
    db.set_submission_verdict(debt, db.VERDICT_RETAKE, "ustaz")

    data = api._hifz_retakes(PHONE)

    assert data["done"] is False and len(data["retakes"]) == 1


# ── Счётчик: чипы прибавляют, вписанное число заменяет ──────────────────────

def test_chips_add_but_typed_number_replaces(student):
    """Случай пользователя 19.09: два раза +10 дали 20, потом он вписал
    число - и раньше оно складывалось, получалось вдвое больше."""
    mw.add_hifz_progress(PHONE, PAGE, 2, 0, 10)
    mw.add_hifz_progress(PHONE, PAGE, 2, 0, 10)
    assert mw.get_hifz_progress(PHONE, PAGE, 2, 0) == 20

    mw.set_hifz_progress(PHONE, PAGE, 2, 0, 20)

    assert mw.get_hifz_progress(PHONE, PAGE, 2, 0) == 20


def test_typed_number_can_correct_an_overshoot(student):
    """Натапал лишнего - дельтой не уменьшить, точным числом можно."""
    mw.add_hifz_progress(PHONE, PAGE, 2, 0, 60)

    mw.set_hifz_progress(PHONE, PAGE, 2, 0, 20)

    assert mw.get_hifz_progress(PHONE, PAGE, 2, 0) == 20


def test_typed_number_is_clamped_to_the_target(student):
    mw.set_hifz_progress(PHONE, PAGE, 2, 0, 500)
    assert mw.get_hifz_progress(PHONE, PAGE, 2, 0) == mw.HIFZ_PROGRESS_TARGET
    mw.set_hifz_progress(PHONE, PAGE, 2, 0, -5)
    assert mw.get_hifz_progress(PHONE, PAGE, 2, 0) == 0


def test_zero_is_a_valid_correction(student):
    """Ноль - это «я ошибся, ничего не было»: дельта такого не умеет."""
    mw.add_hifz_progress(PHONE, PAGE, 2, 0, 40)
    mw.set_hifz_progress(PHONE, PAGE, 2, 0, 0)
    assert mw.get_hifz_progress(PHONE, PAGE, 2, 0) == 0
