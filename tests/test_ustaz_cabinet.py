"""Кабинет устаза: окно последних дней, хвост и место сдачи.

Зачем окно (04.09.2026): reviewed_at проставляется только когда устаз
отвечает реплаем на голосовое в группе. Где так не отвечают, непроверенное
копится с самого старта — на проде это 141 сдача у одного устаза и 289 у
другого, и красный счётчик на двери переставал означать долг за сегодня.
"""

from datetime import timedelta

import core.db as db


CHAT = "-100999001"


def _group():
    db.save_group(CHAT, "Тестовая группа", tasks="m,r,t")
    return db.get_group(CHAT)


def _days_ago(n):
    return (db.get_now() - timedelta(days=n)).date().isoformat()


def _submission(sid, group, msg_id, date, **place):
    db.save_voice_submission(sid, group["id"], CHAT, msg_id, date, **place)


def test_window_keeps_recent_and_folds_the_tail(test_db):
    group = _group()
    sid = db.add_student("Сатар", group["id"], phone="777001")
    _submission(sid, group, 1, _days_ago(0))
    _submission(sid, group, 2, _days_ago(1))
    _submission(sid, group, 3, _days_ago(2))
    _submission(sid, group, 4, _days_ago(3))
    _submission(sid, group, 5, _days_ago(30))

    recent = db.get_pending_voice_reviews([group["id"]])
    older = db.get_pending_voice_reviews([group["id"]], recent=False)

    assert len(recent) == 3          # сегодня, вчера, позавчера
    assert len(older) == 2           # 3 дня назад и месяц назад
    assert db.count_pending_voice_reviews([group["id"]]) == 3
    assert db.count_pending_voice_reviews([group["id"]], recent=False) == 2


def test_reviewed_submission_leaves_the_queue(test_db):
    group = _group()
    sid = db.add_student("Сатар", group["id"], phone="777001")
    _submission(sid, group, 1, _days_ago(0))
    _submission(sid, group, 2, _days_ago(0))

    db.mark_voice_reviewed(CHAT, 1)

    assert db.count_pending_voice_reviews([group["id"]]) == 1


def test_newest_first(test_db):
    """Очередь читается как лента «что пришло», а не как архив."""
    group = _group()
    sid = db.add_student("Сатар", group["id"], phone="777001")
    _submission(sid, group, 1, _days_ago(2))
    _submission(sid, group, 2, _days_ago(0))

    rows = db.get_pending_voice_reviews([group["id"]])

    assert rows[0]["date"] == _days_ago(0)


def test_place_is_stored_and_returned(test_db):
    """Место сдачи 40+40 — то, что устазу и нужно проверять."""
    group = _group()
    sid = db.add_student("Сатар", group["id"], phone="777001")
    _submission(sid, group, 1, _days_ago(0), hifz_page=6, hifz_line=7, hifz_stage=1)

    row = db.get_pending_voice_reviews([group["id"]])[0]

    assert (row["hifz_page"], row["hifz_line"], row["hifz_stage"]) == (6, 7, 1)
    assert row["waited_min"] is not None and row["waited_min"] >= 0


def test_place_empty_for_voice_sent_straight_to_group(test_db):
    """Голосовое, присланное прямо в группу, места не имеет — и это не сбой."""
    group = _group()
    sid = db.add_student("Сатар", group["id"], phone="777001")
    _submission(sid, group, 1, _days_ago(0))

    row = db.get_pending_voice_reviews([group["id"]])[0]

    assert row["hifz_page"] is None
