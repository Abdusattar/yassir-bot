"""/rating - две календарные недели (27.10.2026, Aisha: в /rating первая,
в недельном отчёте вторая - окна были разные)."""
import asyncio
from datetime import date, timedelta

import core.handlers as h
from core.db import save_group, get_group, add_student, add_bonus, group_date


def _send(monkeypatch, group):
    sent = []

    async def fake_send(chat_id, text, *a, **k):
        sent.append(text)
    monkeypatch.setattr(h, "send_message", fake_send)
    asyncio.run(h._send_rating_to("1", group, group["id"], "ru"))
    return sent[0]


def test_rating_last_week_matches_weekly_report(test_db, monkeypatch):
    save_group("-100901", "Группа Р")
    g = get_group("-100901")
    a = add_student("Амина", g["id"], phone="901")
    b = add_student("Аиша", g["id"], phone="902")
    today = date.fromisoformat(group_date())
    monday = today - timedelta(days=today.weekday())
    last_mon = monday - timedelta(days=7)
    # Прошлая неделя: Амина впереди. Восемь дней назад - уже не прошлая
    # неделя, если сегодня не понедельник; ставим в её понедельник.
    add_bonus(a, g["id"], last_mon.isoformat(), 10, "attendance", "online")
    add_bonus(b, g["id"], (monday - timedelta(days=1)).isoformat(), 5, "attendance", "online")
    # Эта неделя: Аиша впереди.
    add_bonus(b, g["id"], monday.isoformat(), 7, "attendance", "online")

    text = _send(monkeypatch, g)
    last, now = text.split("Эта неделя")
    assert last_mon.strftime("%d.%m") in last and (monday - timedelta(days=1)).strftime("%d.%m") in last
    assert last.index("Амина — 10") < last.index("Аиша — 5")
    assert monday.strftime("%d.%m") in now
    assert now.index("Аиша — 7") < now.index("Амина — 0")


def test_rating_empty_this_week(test_db, monkeypatch):
    save_group("-100902", "Группа С")
    g = get_group("-100902")
    add_student("Зухра", g["id"], phone="903")
    text = _send(monkeypatch, g)
    assert "сдач пока нет" in text


def test_week_command_is_last_calendar_week(test_db):
    save_group("-100903", "Группа Т")
    g = get_group("-100903")
    today = date.fromisoformat(group_date())
    monday = today - timedelta(days=today.weekday())
    report = h._period_report("/week", g["id"], "Группа Т", ["m"])
    assert (monday - timedelta(days=7)).strftime("%d.%m") in report
