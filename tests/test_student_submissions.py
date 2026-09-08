"""Кабинет студента «Сдачи»: свои записи, разбор устаза, пересдача.

Экран из макета 01.09 (screen `mine`). Вердикта «принято / на пересдачу» в
базе пока нет — есть только reviewed_at, — поэтому статуса ровно два, а
«Пересдать» доступна всегда. Вердикт отдельным заходом: он меняет контракт с
устазами (пункт 11 макета — не пересдал, следующий этап закрыт; с
07.09.2026 гейт снимает сама пересдача, а не её приём).
"""

import asyncio

import core.db as db
import core.mufradat_api as api


CHAT = "-100555001"


def _group():
    db.save_group(CHAT, "N-1", tasks="m,r,t")
    return db.get_group(CHAT)


def _call(make_app, path, user_id):
    async def run():
        from aiohttp.test_utils import TestClient, TestServer
        client = TestClient(TestServer(make_app()))
        await client.start_server()
        try:
            resp = await client.get(path, headers={"X-Telegram-Init-Data": user_id})
            data = await resp.json() if resp.content_type == "application/json" else None
            return resp.status, data
        finally:
            await client.close()
    return asyncio.run(run())


def _setup(monkeypatch):
    monkeypatch.setattr(api, "validate_init_data", lambda raw, token: {"id": raw})
    monkeypatch.setattr(api, "SUPER_ADMIN_IDS", [])
    return api.build_app


def test_submissions_carry_place_status_and_audio_flags(test_db):
    group = _group()
    sid = db.add_student("Сатар", group["id"], phone="777001")
    db.save_voice_submission(sid, group["id"], CHAT, 10, db.get_date(),
                             file_id="own-file", hifz_page=6, hifz_line=7, hifz_stage=1)

    row = db.get_student_submissions(sid)[0]

    assert (row["hifz_page"], row["hifz_line"], row["hifz_stage"]) == (6, 7, 1)
    assert row["has_audio"] == 1
    assert row["has_review_audio"] == 0
    assert row["reviewed_at"] is None
    assert row["group_title"] == "N-1"


def test_review_from_any_ustaz_reaches_the_student(test_db):
    """Раньше разбор сохранялся только от Умар устаза — студенты остальных
    групп не увидели бы в приложении ничего."""
    group = _group()
    sid = db.add_student("Сатар", group["id"], phone="777001")
    db.add_student("Устаз группы", group["id"], phone="888002")
    db.save_voice_submission(sid, group["id"], CHAT, 10, db.get_date(), file_id="own")

    db.save_submission_review(CHAT, 10, "voice", review_file_id="review-file",
                              review_by="888002")

    row = db.get_student_submissions(sid)[0]
    assert row["review_type"] == "voice"
    assert row["has_review_audio"] == 1
    assert row["review_by_name"] == "Устаз группы"


def test_review_can_be_attached_through_the_picture(test_db):
    """Устаз отвечает реплаем на картинку со строчкой — разбор всё равно
    должен привязаться к сдаче (та же дыра, что и с отметкой «проверено»)."""
    group = _group()
    sid = db.add_student("Сатар", group["id"], phone="777001")
    db.save_voice_submission(sid, group["id"], CHAT, 42, db.get_date(),
                             photo_message_id=41)

    db.save_submission_review(CHAT, 41, "text", review_text="Машаа Аллах",
                              review_by="888002")

    assert db.get_student_submissions(sid)[0]["review_text"] == "Машаа Аллах"


def test_audio_belongs_only_to_its_owner(test_db):
    """Чужую запись не отдаём даже при подобранном id сдачи."""
    group = _group()
    mine = db.add_student("Сатар", group["id"], phone="777001")
    other = db.add_student("Другой", group["id"], phone="777002")
    db.save_voice_submission(mine, group["id"], CHAT, 10, db.get_date(), file_id="own-file")
    sub_id = db.get_student_submissions(mine)[0]["id"]

    assert db.get_submission_audio(sub_id, mine, "own") == "own-file"
    assert db.get_submission_audio(sub_id, other, "own") is None


def test_api_returns_my_submissions(test_db, monkeypatch):
    app = _setup(monkeypatch)
    group = _group()
    sid = db.add_student("Сатар", group["id"], phone="777001")
    db.save_voice_submission(sid, group["id"], CHAT, 10, db.get_date(),
                             file_id="own", hifz_page=6, hifz_line=7, hifz_stage=1)

    status, data = _call(app, "/api/muf/submissions", "777001")

    assert status == 200
    assert len(data["items"]) == 1
    assert data["items"][0]["hifz_page"] == 6


def test_api_refuses_foreign_audio(test_db, monkeypatch):
    """Ответ 404 приходит ДО похода в Telegram — проверка владения в SQL."""
    app = _setup(monkeypatch)
    group = _group()
    mine = db.add_student("Сатар", group["id"], phone="777001")
    db.add_student("Другой", group["id"], phone="777002")
    db.save_voice_submission(mine, group["id"], CHAT, 10, db.get_date(), file_id="own")
    sub_id = db.get_student_submissions(mine)[0]["id"]

    status, _ = _call(app, "/api/muf/submissions/audio?id=%d&kind=own" % sub_id, "777002")

    assert status == 404


class _FakeContent:
    """Ровно тот баг, что был живым 04.09.2026: .content.read(n) при n>0
    отдаёт только первый пришедший чанк, а не n байт - запись обрывалась
    на первых секундах ("play, потом стоп"). Сама read() (без .content) на
    ClientResponse обязана читать до EOF - на это и завязан регресс-тест."""

    def __init__(self, chunks):
        self._chunks = chunks

    async def read(self, n=-1):
        return self._chunks[0]


class _FakeResp:
    def __init__(self, json_data=None, status=200, chunks=None):
        self._json = json_data
        self.status = status
        self.content = _FakeContent(chunks or [b""])
        self._body = b"".join(chunks or [b""])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def json(self):
        return self._json

    async def read(self):
        return self._body


class _FakeSession:
    def __init__(self, chunks):
        self._chunks = chunks

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def get(self, url, params=None):
        if "getFile" in url:
            return _FakeResp(json_data={"ok": True, "result": {"file_path": "voice/f.oga"}})
        return _FakeResp(status=200, chunks=self._chunks)


def test_audio_is_not_truncated_to_the_first_network_chunk(test_db, monkeypatch):
    """Живой баг 04.09.2026: студент жаловался, что запись "играет 2-3
    секунды и всё" - на деле сервер отдавал только первый пришедший от
    Telegram чанк (~16 КБ из ~450 КБ), а не файл целиком. Причина была в
    r.content.read(n) - он не гарантирует n байт, только "что пришло".
    Разгоняем фейковый ответ на несколько чанков, как реальная сеть."""
    app = _setup(monkeypatch)
    group = _group()
    sid = db.add_student("Сатар", group["id"], phone="777001")
    db.save_voice_submission(sid, group["id"], CHAT, 10, db.get_date(), file_id="own")
    sub_id = db.get_student_submissions(sid)[0]["id"]
    chunks = [b"a" * 16093, b"b" * 400000, b"c" * 36464]
    monkeypatch.setattr(api.aiohttp, "ClientSession", lambda: _FakeSession(chunks))

    async def run():
        from aiohttp.test_utils import TestClient, TestServer
        client = TestClient(TestServer(app()))
        await client.start_server()
        try:
            resp = await client.get(
                "/api/muf/submissions/audio?id=%d&kind=own" % sub_id,
                headers={"X-Telegram-Init-Data": "777001"})
            return resp.status, await resp.read()
        finally:
            await client.close()
    status, body = asyncio.run(run())

    assert status == 200
    assert len(body) == sum(len(c) for c in chunks)


def test_submission_counts_feed_the_dashboard_door(test_db):
    """Дверь «Сдачи» показывает два числа: очередь устаза и свой долг.

    Сдачи разнесены по времени намеренно: подряд отправленные голосовые
    считаются одной сдачей (см. merge_submission_series), а здесь проверяются
    именно два разных захода."""
    group = _group()
    sid = db.add_student("Сатар", group["id"], phone="777001")
    today = db.get_date()
    db.save_voice_submission(sid, group["id"], CHAT, 10, today, file_id="a")
    db.save_voice_submission(sid, group["id"], CHAT, 11, today, file_id="b")
    with db.db() as c:
        c.execute("UPDATE voice_submissions SET sent_at=? WHERE message_id=10",
                  ("%sT08:00:00+06:00" % today,))
        c.execute("UPDATE voice_submissions SET sent_at=? WHERE message_id=11",
                  ("%sT21:00:00+06:00" % today,))
    db.mark_voice_reviewed(CHAT, 11)
    with db.db() as c:
        c.execute("UPDATE voice_submissions SET verdict='retake' WHERE message_id=11")

    counts = db.get_submission_counts(sid)

    assert counts["waiting"] == 1        # утренняя ещё ждёт устаза
    assert counts["retake"] == 1         # вечернюю попросили пересдать


def test_submission_counts_are_zero_for_a_newcomer(test_db):
    group = _group()
    sid = db.add_student("Новичок", group["id"], phone="777009")

    assert db.get_submission_counts(sid) == {"waiting": 0, "retake": 0}


def test_voice_series_in_a_group_is_one_submission(test_db):
    """Сдавая 40+40 голосом, студент режет запись на куски. Устаз отвечает
    один раз — и раньше одна часть была «проверена», а три висели «на
    проверке» вечно."""
    group = _group()
    sid = db.add_student("Сатар", group["id"], phone="777001")
    today = db.get_date()
    for n, minute in enumerate(("10:23", "10:28", "10:31"), start=1):
        db.save_voice_submission(sid, group["id"], CHAT, n, today, file_id="v%d" % n)
        with db.db() as c:
            c.execute("UPDATE voice_submissions SET sent_at=? WHERE message_id=?",
                      ("%sT%s:00+06:00" % (today, minute), n))
    db.mark_voice_reviewed(CHAT, 1)          # ответил на первую часть

    merged = db.merge_submission_series(db.get_student_submissions(sid))

    assert len(merged) == 1
    assert merged[0]["series_count"] == 3
    assert merged[0]["reviewed_at"]          # ответ закрывает всю серию
    assert db.get_submission_counts(sid)["waiting"] == 0


def test_a_pause_starts_a_new_submission(test_db):
    """Полчаса тишины — это уже другая сдача, а не продолжение прежней."""
    group = _group()
    sid = db.add_student("Сатар", group["id"], phone="777001")
    today = db.get_date()
    for n, hhmm in ((1, "10:00"), (2, "18:40")):
        db.save_voice_submission(sid, group["id"], CHAT, n, today, file_id="v%d" % n)
        with db.db() as c:
            c.execute("UPDATE voice_submissions SET sent_at=? WHERE message_id=?",
                      ("%sT%s:00+06:00" % (today, hhmm), n))

    merged = db.merge_submission_series(db.get_student_submissions(sid))

    assert len(merged) == 2
    assert db.get_submission_counts(sid)["waiting"] == 2


def test_app_submissions_are_never_merged(test_db):
    """У сдачи из приложения своё место на листе, разбор и пересдача —
    склеить две такие значило бы потерять разбор."""
    group = _group()
    sid = db.add_student("Сатар", group["id"], phone="777001")
    today = db.get_date()
    db.save_voice_submission(sid, group["id"], CHAT, 1, today, file_id="a",
                             hifz_page=15, hifz_line=3, hifz_stage=1)
    db.save_voice_submission(sid, group["id"], CHAT, 2, today, file_id="b",
                             hifz_page=15, hifz_line=4, hifz_stage=1)

    merged = db.merge_submission_series(db.get_student_submissions(sid))

    assert len(merged) == 2


def test_next_part_of_the_same_stage_closes_the_debt(test_db):
    """Этапы 2 и 3 студент сдаёт частями за 2-3 дня (08.09.2026). Устаз
    разбирает первую часть и просит пересдать, студент продолжает добивать
    свои 40+40 — следующая часть той же страницы и есть ответ на замечание.
    Дверь «Сдачи» долга больше не показывает, карточка не висит задачей."""
    group = _group()
    sid = db.add_student("Сатар", group["id"], phone="777001")
    db.save_voice_submission(sid, group["id"], CHAT, 1, db.get_date(), file_id="a",
                             hifz_page=20, hifz_line=0, hifz_stage=3)
    first = db.get_student_submissions(sid)[0]["id"]
    db.set_submission_verdict(first, db.VERDICT_RETAKE, "888002", [{"line": 2, "word": 4}])
    assert db.get_submission_counts(sid)["retake"] == 1

    db.save_voice_submission(sid, group["id"], CHAT, 2, db.get_date(), file_id="b",
                             hifz_page=20, hifz_line=0, hifz_stage=3)

    assert db.get_submission_counts(sid)["retake"] == 0
    row = [r for r in db.get_student_submissions(sid) if r["id"] == first][0]
    assert row["redone"] is True


def test_part_of_another_place_leaves_the_debt(test_db):
    """Сдача другого места ответом не считается — иначе долг гасила бы любая
    работа, а не та, о которой говорил устаз."""
    group = _group()
    sid = db.add_student("Сатар", group["id"], phone="777001")
    db.save_voice_submission(sid, group["id"], CHAT, 1, db.get_date(), file_id="a",
                             hifz_page=20, hifz_line=0, hifz_stage=3)
    first = db.get_student_submissions(sid)[0]["id"]
    db.set_submission_verdict(first, db.VERDICT_RETAKE, "888002")

    db.save_voice_submission(sid, group["id"], CHAT, 2, db.get_date(), file_id="b",
                             hifz_page=21, hifz_line=0, hifz_stage=3)

    assert db.get_submission_counts(sid)["retake"] == 1
    row = [r for r in db.get_student_submissions(sid) if r["id"] == first][0]
    assert row["redone"] is False


def test_retake_debt_survives_the_week_window(test_db):
    """Долг не истекает по сроку: пересдачу считаем за всю историю, даже
    если сама сдача давно вышла из недельного окна экрана."""
    group = _group()
    sid = db.add_student("Сатар", group["id"], phone="777001")
    db.save_voice_submission(sid, group["id"], CHAT, 1, db.get_date(), file_id="a")
    with db.db() as c:
        c.execute("UPDATE voice_submissions SET verdict='retake',"
                  " date=date('now','-40 day') WHERE message_id=1")

    assert db.get_submission_counts(sid)["retake"] == 1
