"""Рейтинг - минутный кэш, своя строка свежая (16.10.2026): пересчёт на
каждом конце сеанса стоил ~0,75 с в главном потоке бота."""

import core.db as db
import core.mufradat_bot as mb


def _score(key, page=20):
    return {"accuracy": 90.0, "correct": 90, "wrong": 10, "n": 100, "attempted": 50,
            "page": page, "last_date": "2026-10-16", "_sort_key": key, "wilson": 0.8}


def test_board_is_reused_within_a_minute(monkeypatch):
    calls = []
    monkeypatch.setattr(mb, "LEADERBOARD_TTL", 60)
    monkeypatch.setattr(mb, "_lb", {"at": 0.0, "key": None, "data": None})
    monkeypatch.setattr(mb, "get_date", lambda: "2026-10-16")
    monkeypatch.setattr(mb, "_compute_leaderboards",
                        lambda: calls.append(1) or {"full": [], "group": [], "names": {}, "groups": {}})
    mb._leaderboards()
    mb._leaderboards()
    assert len(calls) == 1
    # новый учебный день - сразу пересчёт (неактивные выпадают по дням)
    monkeypatch.setattr(mb, "get_date", lambda: "2026-10-17")
    mb._leaderboards()
    assert len(calls) == 2


def test_own_row_is_fresh_and_on_its_new_place(monkeypatch):
    full = [("a", _score(3.0)), ("me", _score(1.0)), ("b", _score(2.0))]
    full.sort(key=lambda x: -x[1]["_sort_key"])
    boards = {"full": full, "group": list(full),
              "names": {"a": "А", "b": "Б", "me": "Я"}, "groups": {"a": "G", "b": "G", "me": "G"}}
    monkeypatch.setattr(mb, "hafiz_phones", lambda: set())
    monkeypatch.setattr(mb, "get_date", lambda: "2026-10-16")
    monkeypatch.setattr(mb, "get_leaderboard", lambda hafiz, user_id: [("me", _score(2.5))])
    out = mb.with_fresh(boards, "me")
    assert [u for u, _ in out["full"]] == ["a", "me", "b"]
    assert [u for u, _ in out["group"]] == ["a", "me", "b"]
    assert [u for u, _ in boards["full"]] == ["a", "b", "me"]      # кэш не тронут
    # не из этого бота - списки как есть, без запроса
    monkeypatch.setattr(mb, "get_leaderboard", lambda **kw: 1 / 0)
    assert mb.with_fresh(boards, "stranger") is boards


def test_people_in_one_query_match_per_student_lookups(test_db):
    g = db.save_group("-1001", "Группа 1", tasks="m,r,t")
    db.update_group_type("-1001", "relaxed")
    db.save_group("-1002", "Подготовительная", tasks="m,r,t")
    db.update_group_type("-1002", "prep")
    gid = db.get_group("-1001")["id"]
    prep = db.get_group("-1002")["id"]
    db.add_student("В группе", gid, phone="111")
    db.add_student("В подготовительной", prep, phone="222")
    db.mark_dm_ok_by_phone("333") if hasattr(db, "mark_dm_ok_by_phone") else None
    names, groups = db.leaderboard_people()
    for phone in ("111", "222", "333", "444"):
        assert (phone in names) == bool(db.find_user_by_phone(phone)), phone
        lg = db.get_learning_group(phone)
        assert groups.get(phone) == (lg["title"] if lg else None), phone


def test_slow_board_reminds_once_a_day(monkeypatch):
    import asyncio
    import core.scheduler as sch
    sent = []

    async def fake_send(chat_id, text, **kw):
        sent.append((chat_id, text))
    monkeypatch.setattr(sch, "send_message", fake_send)
    monkeypatch.setitem(mb.lb_slowest, "sec", 0.4)
    asyncio.run(sch.leaderboard_slow_alert())
    assert sent == []
    monkeypatch.setitem(mb.lb_slowest, "sec", 1.7)
    asyncio.run(sch.leaderboard_slow_alert())
    assert len(sent) == 1 and "1.7" in sent[0][1] and "wiki/leaderboard.md" in sent[0][1]
    assert mb.lb_slowest["sec"] == 0.0          # новый день - новый замер
