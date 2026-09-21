"""«След» действий в приложении (13.09.2026, core/app_trail.py)."""

import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone

import core.app_trail as trail
import core.mufradat_api as api
import core.mushaf_words as mw


def test_add_trail_keeps_known_events_and_drops_garbage(test_hadiths_db):
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    n = trail.add_trail("u1", "male", [
        {"t": now_ms, "e": "open", "n": "tg 390x844"},
        {"t": now_ms, "e": "pick", "p": 51, "l": 7, "s": 2},
        {"t": now_ms, "e": "hack", "p": 1},           # неизвестное событие
        "мусор",                                      # не dict
        {"t": now_ms, "e": "save", "p": "x", "n": "409 retake_pending"},
    ], ua="Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15")
    assert n == 3
    rows = trail.get_trail("u1")
    assert [r["event"] for r in rows] == ["open", "pick", "save"]
    assert rows[0]["note"] == "iOS 18.7 · tg 390x844"
    assert (rows[1]["page"], rows[1]["line"], rows[1]["stage"]) == (51, 7, 2)
    assert rows[2]["page"] is None and rows[2]["note"] == "409 retake_pending"


def test_phone_clock_far_off_falls_back_to_server_time(test_hadiths_db):
    trail.add_trail("u1", "male", [{"t": 12345, "e": "enter"}])
    ts = datetime.fromisoformat(trail.get_trail("u1")[0]["ts"])
    assert abs((datetime.now(timezone.utc) - ts).total_seconds()) < 5


def test_old_rows_are_purged_on_write(test_hadiths_db):
    trail.add_trail("u1", "male", [{"e": "enter"}])
    old = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat()
    with sqlite3.connect(mw.HADITHS_DB) as conn:
        conn.execute("UPDATE app_trail SET ts=?", (old,))
    trail.add_trail("u1", "male", [{"e": "exit"}])
    assert [r["event"] for r in trail.get_trail("u1", hours=24 * 30)] == ["exit"]


def _heartbeat(make_app, user_id, body):
    async def run():
        from aiohttp.test_utils import TestClient, TestServer
        client = TestClient(TestServer(make_app()))
        await client.start_server()
        try:
            kw = {"json": body} if body is not None else {}
            resp = await client.request("POST", "/api/muf/heartbeat",
                                        headers={"X-Telegram-Init-Data": user_id}, **kw)
            return resp.status
        finally:
            await client.close()
    return asyncio.run(run())


def test_heartbeat_takes_trail_batch_and_still_works_without_body(test_db, test_hadiths_db, monkeypatch):
    monkeypatch.setattr(api, "validate_init_data", lambda raw, token: {"id": raw})
    assert _heartbeat(api.build_app, "201", None) == 200
    assert _heartbeat(api.build_app, "201", {"trail": [{"e": "fix", "p": 6, "l": 3, "s": 1}]}) == 200
    rows = trail.get_trail("201")
    assert len(rows) == 1 and rows[0]["event"] == "fix" and rows[0]["page"] == 6


def test_heartbeat_remembers_phone_timezone(test_db, test_hadiths_db, monkeypatch):
    """Пояс телефона (21.09.2026): студент за границей сдаёт в свой вечер, а
    по Бишкеку уже ночь. Пока только копим - настоящее IANA-имя, мусор мимо,
    неизвестный пояс остаётся NULL (= Бишкек)."""
    import core.db as db
    monkeypatch.setattr(api, "validate_init_data", lambda raw, token: {"id": raw})
    monkeypatch.setattr(api, "_tz_seen", {})
    db.save_group("-100777", "TZ Group")
    db.add_student("Арген", db.get_group("-100777")["id"], phone="301")

    def tz_of():
        with db.db() as c:
            return c.execute("SELECT tz FROM users WHERE phone='301'").fetchone()["tz"]

    assert _heartbeat(api.build_app, "301", None) == 200
    assert tz_of() is None
    assert _heartbeat(api.build_app, "301", {"tz": "Mars/Olympus"}) == 200
    assert tz_of() is None
    assert _heartbeat(api.build_app, "301", {"tz": "Europe/London"}) == 200
    assert tz_of() == "Europe/London"
    assert _heartbeat(api.build_app, "301", {"tz": "Asia/Bishkek", "trail": [{"e": "open"}]}) == 200
    assert tz_of() == "Asia/Bishkek"
