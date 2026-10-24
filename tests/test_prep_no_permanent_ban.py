"""В подготовительной вечного бана нет (24.10.2026): ручное удаление
устазом снимается сразу, в остальных группах бан не трогаем."""
import asyncio

import core.db as db
import core.transfers as transfers


def _capture(monkeypatch):
    unbanned = []

    async def fake_unban(chat_id, user_id):
        unbanned.append((str(chat_id), str(user_id)))

    monkeypatch.setattr(transfers, "unban_member", fake_unban)
    return unbanned


def test_ban_in_prep_is_lifted(test_db, monkeypatch):
    db.save_group("-100771", "Prep", tasks="m,r,t")
    db.update_group_type("-100771", "prep")
    unbanned = _capture(monkeypatch)

    assert asyncio.run(transfers.lift_prep_ban("-100771", "555")) is True
    assert unbanned == [("-100771", "555")]


def test_ban_in_regular_group_stays(test_db, monkeypatch):
    db.save_group("-100772", "Pro", tasks="m,r,t")
    db.update_group_type("-100772", "pro")
    unbanned = _capture(monkeypatch)

    assert asyncio.run(transfers.lift_prep_ban("-100772", "555")) is False
    assert asyncio.run(transfers.lift_prep_ban("-100999", "555")) is False
    assert unbanned == []
