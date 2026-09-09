"""Личная насыха несдавшему — не чаще раза в три дня.

Раньше она уходила в личку каждое утро, пока человек не сдаёт. Решение
пользователя 09.09.2026: слишком часто. Проверяем и саму отметку времени,
и то, что отбор получателей идёт ДО обращения к ИИ.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("TELEGRAM_TOKEN", "test")

from core.db import db, get_last_miss_nasiha_at, mark_miss_nasiha_sent
from core.scheduler import MISS_NASIHA_MIN_DAYS, _days_since


def test_no_record_means_send(test_db):
    """Кому ещё не слали — тому можно."""
    assert get_last_miss_nasiha_at("777") is None
    assert _days_since(get_last_miss_nasiha_at("777")) >= MISS_NASIHA_MIN_DAYS


def test_just_sent_blocks_next_morning(test_db):
    """Отправили сегодня — завтра и послезавтра молчим."""
    mark_miss_nasiha_sent("777")
    assert _days_since(get_last_miss_nasiha_at("777")) < MISS_NASIHA_MIN_DAYS


def test_after_cooldown_sends_again(test_db):
    """Прошло три дня — снова можно."""
    mark_miss_nasiha_sent("777")
    with db() as c:
        c.execute("UPDATE miss_nasihas SET last_sent_at=datetime('now', ?) WHERE phone=?",
                  ("-%d days" % (MISS_NASIHA_MIN_DAYS + 1), "777"))
    assert _days_since(get_last_miss_nasiha_at("777")) >= MISS_NASIHA_MIN_DAYS


def test_mark_twice_keeps_one_row(test_db):
    """Повторная отметка обновляет строку, а не плодит вторую."""
    mark_miss_nasiha_sent("777")
    mark_miss_nasiha_sent("777")
    with db() as c:
        rows = c.execute("SELECT COUNT(*) AS n FROM miss_nasihas WHERE phone='777'").fetchone()
    assert rows["n"] == 1
