import asyncio
from datetime import timedelta

import core.db as db
import core.prep as prep


def _setup_prep_group(chat_id="-100888"):
    db.save_group(chat_id, "Test Prep Deadline", tasks="m,r,t")
    db.update_group_type(chat_id, "prep")
    return db.get_group(chat_id)


def _capture(monkeypatch):
    sent = []

    async def fake_send_message(chat_id, text, reply_to_message_id=None):
        sent.append((chat_id, text))

    async def fake_ban(chat_id, user_id):
        return None

    async def fake_unban(chat_id, user_id):
        return None

    async def fake_link():
        return "https://t.me/testbot?start=go"

    monkeypatch.setattr(prep, "send_message", fake_send_message)
    monkeypatch.setattr(prep, "ban_member", fake_ban)
    monkeypatch.setattr(prep, "unban_member", fake_unban)
    monkeypatch.setattr(prep, "get_dm_start_link", fake_link)
    return sent


def _join_days_ago(days):
    return (db.get_now() - timedelta(days=days)).date().isoformat()


def _give_full_days(sid, group_id, n, start_days_ago):
    """n подряд идущих ПОЛНЫХ дней начиная с joined_date (start_days_ago),
    чтобы попасть в диапазон count_report_days_since (date >= since_date)."""
    for i in range(n):
        d = (db.get_now() - timedelta(days=start_days_ago - i)).date().isoformat()
        db.save_report(sid, group_id, d, {"m": True, "r": True, "t": True})


def test_zero_full_days_fails_exactly_at_14(test_db, monkeypatch):
    """12.08.2026: 14 дней достаточно тому, кто ничего полного не сдал -
    без продления."""
    g = _setup_prep_group()
    sid = db.add_student("НульДней", g["id"], phone="d1")
    with db.db() as c:
        c.execute("UPDATE user_groups SET joined_date=? WHERE user_id=? AND group_id=?",
                   (_join_days_ago(14), sid, g["id"]))
    _capture(monkeypatch)

    assert db.count_report_days_since(sid, g["id"], _join_days_ago(14)) == 0
    asyncio.run(prep.check_prep_students())

    assert db.find_by_phone("d1", g["id"]) is None  # деактивирован


def test_three_full_days_extends_deadline_to_17(test_db, monkeypatch):
    """3 полных дня -> дедлайн 14+3=17. На 16-й день ещё не кикаем."""
    g = _setup_prep_group("-100889")
    sid = db.add_student("ТриДня", g["id"], phone="d2")
    with db.db() as c:
        c.execute("UPDATE user_groups SET joined_date=? WHERE user_id=? AND group_id=?",
                   (_join_days_ago(16), sid, g["id"]))
    _give_full_days(sid, g["id"], 3, 16)
    assert db.count_report_days_since(sid, g["id"], _join_days_ago(16)) == 3
    _capture(monkeypatch)

    asyncio.run(prep.check_prep_students())

    assert db.find_by_phone("d2", g["id"]) is not None  # ещё активен, не кикнут


def test_three_full_days_fails_at_17(test_db, monkeypatch):
    g = _setup_prep_group("-100890")
    sid = db.add_student("ТриДняПросрочен", g["id"], phone="d3")
    with db.db() as c:
        c.execute("UPDATE user_groups SET joined_date=? WHERE user_id=? AND group_id=?",
                   (_join_days_ago(17), sid, g["id"]))
    _give_full_days(sid, g["id"], 3, 17)
    assert db.count_report_days_since(sid, g["id"], _join_days_ago(17)) == 3
    _capture(monkeypatch)

    asyncio.run(prep.check_prep_students())

    assert db.find_by_phone("d3", g["id"]) is None  # дедлайн истёк, кикнут
