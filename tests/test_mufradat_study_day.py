"""Счётчик тренажёра слов живёт по учебным суткам (до трёх ночи — ещё вчера),
как все зачёты (core/db.py:get_date). 11.10.2026: студент пожаловался, что
счётчик обнулялся в полночь — core/mufradat.py брал календарную дату."""
from datetime import datetime, timedelta

import pytz

import core.db as db
import core.mufradat as muf


def _at(monkeypatch, hh, mm):
    tz = pytz.timezone(db.TZ)
    now = tz.localize(datetime(2026, 10, 11, hh, mm))
    monkeypatch.setattr(db, "_study_now", lambda: now - timedelta(hours=db.STUDY_DAY_END_HOUR))


def test_after_midnight_still_yesterday(monkeypatch):
    _at(monkeypatch, 0, 30)
    assert muf._today() == "2026-10-10"
    assert muf._days_since("2026-10-10") == 0


def test_after_three_new_day(monkeypatch):
    _at(monkeypatch, 3, 5)
    assert muf._today() == "2026-10-11"
    assert muf._days_since("2026-10-10") == 1
