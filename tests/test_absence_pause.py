"""Узр кнопкой и пауза «Цикл» (03.11.2026, решение пользователя; core/absence.py).

Пауза - только сёстрам: дни паузы не пропуски, напоминаний нет, группе не
видно, серия не рвётся и не растёт, в лимит узров не идёт. Конец сам -
первая сдача после нажатия или 15 дней.
"""
import asyncio

import config
import core.absence as absence
import core.db as db
import core.mufradat_api as api


def _group(chat_id="-100771", title="Мохидил 1", tasks="m,r,t"):
    db.save_group(chat_id, title, tasks=tasks)
    db.update_group_type(chat_id, "relaxed")
    return db.get_group(chat_id)


def _today(monkeypatch, day):
    monkeypatch.setattr(db, "get_date", lambda *_a: day)
    monkeypatch.setattr(db, "group_date", lambda: day)


def _full(sid, gid, day):
    db.save_report(sid, gid, day, {"m": True, "r": True, "t": True})


def _pause_rows(sid):
    with db.db() as c:
        return [r["date"] for r in c.execute(
            "SELECT date FROM score_events WHERE student_id=? AND category='pause' ORDER BY date",
            (sid,)).fetchall()]


def test_pause_writes_only_today_and_tick_adds_next_day(test_db, monkeypatch):
    g = _group()
    sid = db.add_student("Айша", g["id"], phone="771")
    _today(monkeypatch, "2026-11-09")
    p = absence.start_pause(sid, g["id"])
    assert p["start_date"] == "2026-11-09"
    assert _pause_rows(sid) == ["2026-11-09"]       # наперёд дни не пишем
    absence.tick()
    assert _pause_rows(sid) == ["2026-11-09"]       # повтор безвреден
    _today(monkeypatch, "2026-11-11")               # пропущенный запуск догоняется
    absence.tick()
    assert _pause_rows(sid) == ["2026-11-09", "2026-11-10", "2026-11-11"]
    assert absence.pause_status(sid)["day"] == 3
    # Второе нажатие не заводит вторую паузу.
    assert absence.start_pause(sid, g["id"])["id"] == p["id"]


def test_pause_closes_after_15_days(test_db, monkeypatch):
    g = _group()
    sid = db.add_student("Айша", g["id"], phone="771")
    _today(monkeypatch, "2026-11-01")
    absence.start_pause(sid, g["id"])
    _today(monkeypatch, "2026-11-15")               # 15-й день - ещё пауза
    absence.tick()
    assert absence.active_pause(sid) is not None
    assert _pause_rows(sid)[-1] == "2026-11-15"
    _today(monkeypatch, "2026-11-16")               # 16-й - снята, день не пишется
    absence.tick()
    assert absence.active_pause(sid) is None
    assert len(_pause_rows(sid)) == 15


def test_first_submission_closes_pause(test_db, monkeypatch):
    g = _group()
    sid = db.add_student("Айша", g["id"], phone="771")
    _today(monkeypatch, "2026-11-09")
    _full(sid, g["id"], "2026-11-09")               # сдала до нажатия
    absence.start_pause(sid, g["id"])
    _full(sid, g["id"], "2026-11-09")               # тот же зачёт ещё раз - дубль, не новая сдача
    assert absence.active_pause(sid) is not None
    _today(monkeypatch, "2026-11-12")
    # Устаз принял старую запись задним числом - паузу не закрывает.
    db.save_report(sid, g["id"], "2026-11-12", {"r": True}, closes_pause=False)
    assert absence.active_pause(sid) is not None
    # Зачёт за прошлый день (не «сегодня») тоже не закрывает.
    db.save_report(sid, g["id"], "2026-11-08", {"m": True})
    assert absence.active_pause(sid) is not None
    db.save_report(sid, g["id"], "2026-11-12", {"m": True})
    p = absence.active_pause(sid)
    assert p is None
    with db.db() as c:
        assert c.execute("SELECT close_reason FROM absence_pauses").fetchone()[0] == "submitted"


def test_pause_day_is_not_missed_and_not_reminded(test_db, monkeypatch):
    g = _group()
    sid = db.add_student("Айша", g["id"], phone="771")
    other = db.add_student("Марьям", g["id"], phone="772")
    _today(monkeypatch, "2026-11-09")
    absence.start_pause(sid, g["id"])
    missing = [s["id"] for s, _ in db.get_missing_students(g["id"], ["m", "r", "t"], "2026-11-09")]
    assert sid not in missing and other in missing
    assert "2026-11-09" in db._active_dates(sid)    # счётчики пропусков видят день


def test_group_report_and_summary_hide_paused(test_db, monkeypatch):
    g = _group()
    sid = db.add_student("Айша", g["id"], phone="771")
    db.add_student("Марьям", g["id"], phone="772")
    _today(monkeypatch, "2026-11-09")
    absence.start_pause(sid, g["id"])
    report = db.format_daily_report(g["id"], g["title"], ["m", "r", "t"], "2026-11-09")
    assert "Айша" not in report and "Марьям" in report
    assert "/1" in report.split("Сдали хоть что-то:")[1].split("\n")[0]
    counts = db.get_daily_task_counts(g["id"], ["m", "r", "t"], "2026-11-09")
    assert [c["name"] for c in counts] == ["Марьям"]


def test_streak_bridges_pause(test_db, monkeypatch):
    g = _group()
    sid = db.add_student("Айша", g["id"], phone="771")
    for d in ("2026-11-01", "2026-11-02", "2026-11-03"):
        _full(sid, g["id"], d)
    _today(monkeypatch, "2026-11-04")
    absence.start_pause(sid, g["id"])
    for d in ("2026-11-05", "2026-11-06"):
        _today(monkeypatch, d)
        absence.tick()
    _today(monkeypatch, "2026-11-07")
    _full(sid, g["id"], "2026-11-07")               # закрывает паузу
    assert absence.active_pause(sid) is None
    assert db.get_streak_days(sid, g["id"], ["m", "r", "t"], "2026-11-07") == 4
    assert db.get_group_streaks(g["id"], ["m", "r", "t"], "2026-11-07").get(sid) == 4
    # Без паузы тот же разрыв серию рвёт.
    other = db.add_student("Марьям", g["id"], phone="772")
    for d in ("2026-11-01", "2026-11-02", "2026-11-03", "2026-11-07"):
        _full(other, g["id"], d)
    assert db.get_streak_days(other, g["id"], ["m", "r", "t"], "2026-11-07") == 1


def test_excuse_rule_and_pause_not_in_limit(test_db, monkeypatch):
    g = _group()
    sid = db.add_student("Айша", g["id"], phone="771")
    _today(monkeypatch, "2026-11-02")
    absence.start_pause(sid, g["id"])
    assert absence.excuse_status(sid, g["id"])["left"] == 3   # пауза в лимит не идёт
    assert absence.apply_excuse(sid, g["id"]) == "already"     # «узр» текстом на паузе
    assert absence.excuse_status(sid, g["id"])["left"] == 3
    with db.db() as c:
        c.execute("UPDATE absence_pauses SET closed_at='x'")
    assert absence.apply_excuse(sid, g["id"], "болею") == "ok"
    assert absence.apply_excuse(sid, g["id"]) == "already"
    for d in ("2026-11-03", "2026-11-04"):
        _today(monkeypatch, d)
        assert absence.apply_excuse(sid, g["id"]) == "ok"
    _today(monkeypatch, "2026-11-05")
    assert absence.apply_excuse(sid, g["id"]) == "limit"


# ── API ───────────────────────────────────────────────────────────────────────

def _call(method, path, user_id, body=None):
    async def run():
        from aiohttp.test_utils import TestClient, TestServer
        client = TestClient(TestServer(api.build_app()))
        await client.start_server()
        try:
            resp = await client.request(method, path, json=body,
                                        headers={"X-Telegram-Init-Data": user_id})
            return resp.status, (await resp.json())
        finally:
            await client.close()
    return asyncio.run(run())


def _auth(monkeypatch):
    monkeypatch.setattr(api, "validate_init_data", lambda raw, token: {"id": raw})
    sent = []

    async def fake_send(chat_id, text, *a, **kw):
        sent.append((chat_id, text))
    import core.tg as tg
    monkeypatch.setattr(tg, "send_message", fake_send)
    return sent


def test_cycle_only_for_sisters(test_db, monkeypatch):
    g = _group()
    db.add_student("Абдулла", g["id"], phone="881")
    _auth(monkeypatch)
    monkeypatch.setattr(config, "IS_FEMALE", False)
    st, data = _call("GET", "/api/muf/month", "881")
    assert data["absence"]["cycle_allowed"] is False
    st, _ = _call("POST", "/api/muf/absence/cycle", "881", {})
    assert st == 403
    monkeypatch.setattr(config, "IS_FEMALE", True)
    st, data = _call("POST", "/api/muf/absence/cycle", "881", {})
    assert st == 200 and data["absence"]["pause"]["day"] == 1
    assert data["pauses"] == [db.get_date()]


def test_excuse_from_app_tells_group_without_reason(test_db, monkeypatch):
    g = _group()
    db.add_student("Айша", g["id"], phone="771")
    sent = _auth(monkeypatch)
    st, data = _call("POST", "/api/muf/absence/excuse", "771", {"reason": "к врачу"})
    assert st == 200 and data["result"] == "ok"
    assert data["absence"]["excuse"]["today"] is True
    assert len(sent) == 1 and "Айша" in sent[0][1] and "врачу" not in sent[0][1]
    st, data = _call("POST", "/api/muf/absence/excuse", "771", {})
    assert data["result"] == "already" and len(sent) == 1


def test_no_cycle_in_prep(test_db, monkeypatch):
    """В подготовительной паузы нет: там свой срок, пауза его не сдвигает."""
    db.save_group("-100772", "Подготовительная", tasks="m,r,t")
    db.update_group_type("-100772", "prep")
    g = db.get_group("-100772")
    db.add_student("Айша", g["id"], phone="773")
    _auth(monkeypatch)
    monkeypatch.setattr(config, "IS_FEMALE", True)
    st, data = _call("GET", "/api/muf/month", "773")
    assert data["absence"]["cycle_allowed"] is False
    st, _ = _call("POST", "/api/muf/absence/cycle", "773", {})
    assert st == 403


def test_ustaz_students_strip_gets_pause_days(test_db, monkeypatch):
    g = _group()
    sid = db.add_student("Айша", g["id"], phone="771")
    _today(monkeypatch, db.group_date())
    absence.start_pause(sid, g["id"])
    rows = db.get_group_month_progress(g["id"])
    assert next(r for r in rows if r["id"] == sid)["pause_days"] == [db.get_date()]
