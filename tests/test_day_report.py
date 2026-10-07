"""Мини-отчёт по дню (07.10.2026): что сдано и когда, чего не хватило, узр,
урок, след. Повод - Сумая (2 группа Асмы): «я всё сдаю», а не хватало
повторения, и это было видно только по базе."""
import asyncio

import core.app_trail as trail
import core.db as db
import core.mufradat_api as api
from core.day_report import day_report, study_day_bounds_utc


def _group(chat_id="-100901", title="N-1", tasks="m,r,t"):
    db.save_group(chat_id, title, tasks=tasks)
    db.update_group_type(chat_id, "relaxed")
    return db.get_group(chat_id)


def test_partial_day_names_missing_task_and_times(test_db, test_hadiths_db, monkeypatch):
    g = _group()
    sid = db.add_student("Сумая", g["id"], phone="777")
    monkeypatch.setattr(db, "get_date", lambda: "2026-10-06")
    db.save_report(sid, g["id"], "2026-10-06", {"m": True, "t": True})
    db.save_voice_submission(sid, g["id"], g["chat_id"], 5, "2026-10-06", file_id="f",
                             hifz_page=10, hifz_line=9, hifz_stage=1)
    r = day_report(sid, g["id"], "2026-10-06", phone="777")
    by = {t["key"]: t for t in r["tasks"]}
    assert [t["key"] for t in r["tasks"]] == ["m", "r", "t"]
    assert by["m"]["done"] and by["t"]["done"] and not by["r"]["done"]
    assert by["m"]["at"] and len(by["m"]["at"]) == 5          # ЧЧ:ММ по местному
    assert "стр. 10, строка 10" in by["m"]["detail"] and "на проверке" in by["m"]["detail"]
    assert r["excuse"] is None and r["lesson"] is False


def test_excuse_lesson_and_trail(test_db, test_hadiths_db, monkeypatch):
    g = _group()
    sid = db.add_student("Абдулла", g["id"], phone="778")
    db.add_bonus(sid, g["id"], "2026-10-06", 0, "excuse", note="болел")
    db.add_bonus(sid, g["id"], "2026-10-06", 5, "attendance", "online")
    since, until = study_day_bounds_utc("2026-10-06")
    assert since.startswith("2026-10-05T21:00") and until.startswith("2026-10-06T21:00")
    trail.add_trail("778", "male", [{"e": "open", "n": "Android 14 · tg 392x766", "t": 0},
                                    {"e": "page", "p": 3}])
    # Запись следа ложится «сейчас» - подвинем её внутрь проверяемого дня.
    import sqlite3
    import core.mushaf_words as mw
    with sqlite3.connect(mw.HADITHS_DB) as conn:
        conn.execute("UPDATE app_trail SET ts='2026-10-06T01:05:13+00:00'")
    r = day_report(sid, g["id"], "2026-10-06", phone="778")
    assert r["excuse"] == "болел" and r["lesson"] is True
    # Навигация по листам (page) не показывается; устройство - из User-Agent,
    # в тесте его нет ("other").
    assert len(r["trail"]) == 1 and r["trail"][0].startswith("07:05 · открыл приложение")


def _call(path, user_id):
    async def run():
        from aiohttp.test_utils import TestClient, TestServer
        client = TestClient(TestServer(api.build_app()))
        await client.start_server()
        try:
            resp = await client.request("GET", path, headers={"X-Telegram-Init-Data": user_id})
            return resp.status, (await resp.json())
        finally:
            await client.close()
    return asyncio.run(run())


def test_api_student_and_ustaz_see_the_same_day(test_db, test_hadiths_db, monkeypatch):
    monkeypatch.setattr(api, "validate_init_data", lambda raw, token: {"id": raw})
    monkeypatch.setattr(api, "SUPER_ADMIN_IDS", [])
    g = _group()
    sid = db.add_student("Сумая", g["id"], phone="777")
    db.add_group_admin(g["id"], "999")
    db.save_report(sid, g["id"], "2026-10-06", {"m": True})
    st, mine = _call("/api/muf/day?date=2026-10-06", "777")
    assert st == 200 and [t["done"] for t in mine["tasks"]] == [True, False, False]
    st, his = _call("/api/muf/ustaz/day?id=%d&group=%d&date=2026-10-06" % (sid, g["id"]), "999")
    assert st == 200 and his["tasks"] == mine["tasks"]
    assert _call("/api/muf/day?date=06.10", "777")[0] == 400
    assert _call("/api/muf/ustaz/day?id=%d&group=%d&date=2026-10-06" % (sid, g["id"]), "777")[0] == 403
    st, month = _call("/api/muf/month", "777")
    assert st == 200 and month["tasks_total"] == 3
