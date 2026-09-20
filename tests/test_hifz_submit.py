import asyncio

import core.db as db
import core.mufradat_bot as mb


def _setup_group(chat_id="-100902", tasks="m,r,t"):
    db.save_group(chat_id, "Test Hifz Group", tasks=tasks)
    db.update_group_type(chat_id, "pro")
    return db.get_group(chat_id)


def _capture(monkeypatch, voice_ok=True):
    """Подменяет и конвертацию (ffmpeg на машине с тестами не нужен), и обе
    отправки в Telegram. Возвращает список отправленного."""
    sent = {"photo": [], "voice": []}

    async def fake_transcode(audio_bytes):
        return b"OGG:" + audio_bytes

    async def fake_send_photo(chat_id, photo_bytes, filename, caption=None, reply_to_message_id=None):
        sent["photo"].append((chat_id, caption))
        return {"ok": True, "result": {"message_id": 111}}

    async def fake_send_voice(chat_id, voice_bytes, caption=None, reply_to_message_id=None):
        sent["voice"].append((chat_id, caption, voice_bytes, reply_to_message_id))
        if not voice_ok:
            return {"ok": False, "description": "boom"}
        return {"ok": True, "result": {"message_id": 222, "voice": {"file_id": "FID"}}}

    monkeypatch.setattr(mb, "transcode_to_ogg", fake_transcode)
    monkeypatch.setattr(mb, "send_photo_bytes", fake_send_photo)
    monkeypatch.setattr(mb, "send_voice_bytes", fake_send_voice)
    return sent


def test_hifz_submit_sends_photo_and_voice_and_credits_task(test_db, monkeypatch):
    group = _setup_group()
    uid = db.add_student("Test Student", group["id"], phone="999000111")
    sent = _capture(monkeypatch)

    res = asyncio.run(mb.submit_hifz_recording("999000111", b"AUDIO", b"PNG", 5, 2, 1))

    assert res["ok"] is True
    assert res["credited"] is True
    assert sent["photo"][0][1] == "Test Student — стр. 5, строка 3"
    assert sent["voice"][0][1] == "Test Student, заучивание + (через YassirApp, 40+40)."
    assert sent["voice"][0][2] == b"OGG:AUDIO"
    assert sent["voice"][0][3] == 111  # голосовое реплаем к картинке

    assert db.get_today_report(uid, group["id"])["m"] is True


def test_hifz_submit_second_time_same_day_still_sends_but_no_second_credit(test_db, monkeypatch):
    group = _setup_group()
    db.add_student("Test Student", group["id"], phone="999000111")
    sent = _capture(monkeypatch)

    asyncio.run(mb.submit_hifz_recording("999000111", b"A1", b"P", 5, 2, 1))
    res = asyncio.run(mb.submit_hifz_recording("999000111", b"A2", b"P", 5, 3, 1))

    assert res["ok"] is True
    assert res["credited"] is False
    # Каждая сдача - отдельный материал устазу, вторая тоже уходит в группу,
    # но уже без "заучивание +" - второго зачёта за день нет.
    assert len(sent["voice"]) == 2
    assert sent["voice"][1][1] == "Test Student, стр. 5, строка 4 (через YassirApp, 40+40)."


def test_hifz_submit_saves_voice_submission_for_ustaz_reply(test_db, monkeypatch):
    group = _setup_group()
    uid = db.add_student("Test Student", group["id"], phone="999000111")
    _capture(monkeypatch)

    asyncio.run(mb.submit_hifz_recording("999000111", b"AUDIO", None, 5, 2, 1))

    with db.db() as c:
        row = c.execute(
            "SELECT student_id, message_id, file_id, reviewed_at FROM voice_submissions"
            " WHERE group_id=?", (group["id"],)
        ).fetchone()
    assert row["student_id"] == uid
    assert row["message_id"] == 222
    assert row["file_id"] == "FID"
    assert row["reviewed_at"] is None  # ждёт реплая устаза, как обычная голосовая


def test_hifz_submit_bad_audio_does_not_reach_group(test_db, monkeypatch):
    group = _setup_group()
    db.add_student("Test Student", group["id"], phone="999000111")
    sent = _capture(monkeypatch)

    async def failed_transcode(audio_bytes):
        return None

    monkeypatch.setattr(mb, "transcode_to_ogg", failed_transcode)
    res = asyncio.run(mb.submit_hifz_recording("999000111", b"BROKEN", b"P", 5, 2, 1))

    assert res == {"ok": False, "error": "bad_audio"}
    assert sent["photo"] == [] and sent["voice"] == []


def test_hifz_submit_no_credit_if_send_failed(test_db, monkeypatch):
    group = _setup_group()
    uid = db.add_student("Test Student", group["id"], phone="999000111")
    _capture(monkeypatch, voice_ok=False)

    res = asyncio.run(mb.submit_hifz_recording("999000111", b"AUDIO", b"P", 5, 2, 1))

    assert res == {"ok": False, "error": "send_failed"}
    assert db.get_today_report(uid, group["id"]) is None


def test_hifz_submit_noop_without_group_or_task(test_db, monkeypatch):
    _capture(monkeypatch)
    assert asyncio.run(mb.submit_hifz_recording("nobody", b"A", None, 5, 0, 1)) == {
        "ok": False, "error": "no_group"
    }

    group = _setup_group(chat_id="-100903", tasks="r,t")  # без "m"
    db.add_student("Other Student", group["id"], phone="999000222")
    assert asyncio.run(mb.submit_hifz_recording("999000222", b"A", None, 5, 0, 1)) == {
        "ok": False, "error": "task_off"
    }


def test_hifz_place_wording_per_stage():
    assert mb._hifz_place(5, 2, 1) == "стр. 5, строка 3"
    assert mb._hifz_place(5, 2, 2) == "стр. 5, верхняя половина"
    assert mb._hifz_place(5, 9, 2) == "стр. 5, нижняя половина"
    assert mb._hifz_place(5, 0, 3) == "стр. 5, вся страница"


def test_hifz_submit_duration_falls_back_to_client_ms(test_db, monkeypatch):
    """Telegram отдал duration=0 (бывает у браузерных файлов, 16.09.2026) -
    берём замер приложения; когда Telegram дал длину, она главнее."""
    group = _setup_group()
    db.add_student("Тест", group["id"], phone="999000111")
    durations = iter([0, 77])
    msg_ids = iter([222, 223])

    async def fake_transcode(audio_bytes):
        return audio_bytes

    async def fake_send_voice(chat_id, voice_bytes, caption=None, reply_to_message_id=None):
        return {"ok": True, "result": {"message_id": next(msg_ids),
                                       "voice": {"file_id": "FID", "duration": next(durations)}}}

    monkeypatch.setattr(mb, "transcode_to_ogg", fake_transcode)
    monkeypatch.setattr(mb, "send_voice_bytes", fake_send_voice)
    asyncio.run(mb.submit_hifz_recording("999000111", b"A", None, 5, 2, 1, client_ms=12_400))
    asyncio.run(mb.submit_hifz_recording("999000111", b"B", None, 5, 2, 1, client_ms=12_400))
    with db.db() as c:
        rows = c.execute("SELECT duration FROM voice_submissions ORDER BY id").fetchall()
    assert [r[0] for r in rows] == [12, 77]


# ── Запись дошла не целиком (17.09.2026, Саламат: страница 14 с вместо ~2 мин) ──

def _lengths(monkeypatch, first, via_file=None):
    """Подменяет замер длины: первая переделка даёт first секунд, переделка
    через файл - via_file (None - такой не было)."""
    calls = []

    async def fake_seconds(data):
        return via_file if data.startswith(b"FILE:") else first

    async def fake_ffmpeg(codec_args, audio_bytes, via_file=False):
        calls.append(via_file)
        return b"FILE:" + audio_bytes
    monkeypatch.setattr(mb, "audio_seconds", fake_seconds)
    monkeypatch.setattr(mb, "_run_ffmpeg", fake_ffmpeg)
    return calls


def test_lost_tail_is_redone_via_file_and_sent_whole(test_db, monkeypatch):
    g = _setup_group()
    db.add_student("Саламат", g["id"], phone="999000111")
    sent = _capture(monkeypatch)
    calls = _lengths(monkeypatch, first=14.4, via_file=150.0)
    res = asyncio.run(mb.submit_hifz_recording("999000111", b"A", b"P", 21, 0, 3, client_ms=151000))
    assert res["ok"] is True and calls == [True]
    assert sent["voice"][0][2].startswith(b"FILE:")          # ушла переделка через файл


def test_still_short_after_file_is_incomplete_and_not_sent(test_db, monkeypatch):
    g = _setup_group()
    db.add_student("Саламат", g["id"], phone="999000111")
    sent = _capture(monkeypatch)
    _lengths(monkeypatch, first=14.4, via_file=14.4)
    res = asyncio.run(mb.submit_hifz_recording("999000111", b"A", b"P", 21, 0, 3, client_ms=151000))
    assert res == {"ok": False, "error": "incomplete"}
    assert sent["voice"] == [] and sent["photo"] == []
    assert not (db.get_today_report(db.find_user_by_phone("999000111")["id"], g["id"]) or {}).get("m")


def test_page_shorter_than_minimum_is_refused(test_db, monkeypatch):
    g = _setup_group()
    db.add_student("Саламат", g["id"], phone="999000111")
    sent = _capture(monkeypatch)
    _lengths(monkeypatch, first=15.0)
    res = asyncio.run(mb.submit_hifz_recording("999000111", b"A", b"P", 21, 0, 3, client_ms=15500))
    assert res["error"] == "too_short" and sent["voice"] == []
    # строка в 5 секунд - нормально, быстрый чтец
    ok = asyncio.run(mb.submit_hifz_recording("999000111", b"A", b"P", 21, 0, 1, client_ms=5200))
    assert ok["ok"] is True


def test_lost_tail_rule_leaves_room_for_small_differences():
    assert mb.lost_tail(14.4, 151000)
    assert not mb.lost_tail(146, 151000)       # 5 с разницы, но это 97%
    assert not mb.lost_tail(8, 12000)          # 67%, но всего 4 с
    assert not mb.lost_tail(None, 151000)      # не смогли замерить - не мешаем
    assert mb.lost_tail(0.0, 151000)           # пустой результат - потеряно всё


def test_сдача_из_чужого_бота_говорит_прямо(test_db, tmp_path, monkeypatch, fresh_db):
    """17.09.2026, Динара: открыла приложение через мужской бот, учится в
    женском. Вместо «нет группы» - «не тот бот»."""
    import sqlite3
    import config
    other = tmp_path / "quran_female.db"
    c = sqlite3.connect(other)
    c.executescript("""
        CREATE TABLE users(id INTEGER PRIMARY KEY, name TEXT, phone TEXT);
        CREATE TABLE groups(id INTEGER PRIMARY KEY, group_type TEXT);
        CREATE TABLE user_groups(user_id INT, group_id INT, role TEXT, active INT);
        INSERT INTO users VALUES(1, 'Динара', '555');
        INSERT INTO groups VALUES(6, 'relaxed');
        INSERT INTO user_groups VALUES(1, 6, 'student', 1);
    """)
    c.commit(); c.close()
    own = tmp_path / "quran_male.db"
    monkeypatch.setattr(config, "PROFILE", "male")
    monkeypatch.setattr(db, "DB", fresh_db(own))
    res = asyncio.run(mb.submit_hifz_recording("555", b"a", None, 10, 1, 1))
    assert res == {"ok": False, "error": "wrong_bot"}
    assert db.other_bot_member("555") and not db.other_bot_member("777")
    db.mark_dm_ok_by_phone("555")
    db.mark_dm_ok_by_phone("777")
    assert [r["phone"] for r in db.get_return_nudge_candidates()] == ["777"]
