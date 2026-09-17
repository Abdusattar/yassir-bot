"""Лекции по группам и открытие предметов по позиции заучивания (17.09.2026)."""
import asyncio

import core.db as db
import core.curriculum as cur
import core.scheduler as sched
import core.tg as tg

OLD, NEW = "-100810001", "-100810002"


def _parts(subject="j", topics=("Введение", "Сколько всего мест выхода", "Горло", "Губы"), published=2):
    for i, topic in enumerate(topics):
        with db.db() as c:
            c.execute(
                "INSERT INTO curriculum_parts(subject, chapter, topic, part_number, part_total,"
                " order_index, content, published_at) VALUES(?,'Глава',?,1,1,?,?,?)",
                (subject, topic, i + 1, "текст " + topic, "2026-07-01" if i < published else None))


def _groups():
    db.save_group(OLD, "N-1", tasks="m,r,t,j")
    db.save_group(NEW, "G-12", tasks="m,r,t")
    for chat in (OLD, NEW):
        db.update_group_type(chat, "relaxed")
    return db.get_group(OLD), db.get_group(NEW)


def _capture(monkeypatch):
    sent = []

    async def fake_send(chat_id, text, **kw):
        sent.append((str(chat_id), text))
        return {"ok": True}
    monkeypatch.setattr(sched, "send_message", fake_send)
    monkeypatch.setattr(tg, "send_message", fake_send)
    monkeypatch.setattr(sched, "SUPER_ADMIN_IDS", ["900001"])
    return sent


def _pointers(monkeypatch, pages):
    import core.mushaf_words as mw
    monkeypatch.setattr(mw, "get_hifz_pointer", lambda phone: {"page": pages[phone]} if phone in pages else None)


def test_backfill_keeps_everything_for_groups_already_studying(test_db):
    old, new = _groups()
    _parts()
    cur.backfill()
    assert sorted(cur.topics("j", old["id"])) == ["Введение", "Сколько всего мест выхода"]
    assert cur.topics("j", new["id"]) == []
    assert len(cur.topics("j")) == 2                      # устазу - всё опубликованное


def test_each_group_gets_its_own_next_lecture(test_db, monkeypatch):
    old, new = _groups()
    _parts()
    cur.backfill()
    cur.announce_start(new["id"], "j", today="2026-10-01")          # старт 08.10
    monkeypatch.setattr(cur, "get_date", lambda: "2026-10-08")
    sent = _capture(monkeypatch)

    asyncio.run(sched.publish_curriculum_parts())

    got = dict((chat, text) for chat, text in sent if chat in (OLD, NEW))
    assert "текст Горло" in got[OLD]                      # ведущая группа - третья лекция
    assert "текст Введение" in got[NEW]                   # новая - первая
    assert cur.topics("j", new["id"]) == ["Введение"]
    # вводная лекция без букв: задание «j» ещё не включено
    assert "j" not in db.get_group_tasks(db.get_group(NEW))


def test_group_not_yet_started_gets_nothing(test_db, monkeypatch):
    old, new = _groups()
    _parts()
    cur.backfill()
    cur.announce_start(new["id"], "j", today="2026-10-01")
    monkeypatch.setattr(cur, "get_date", lambda: "2026-10-02")      # неделя ещё не прошла
    sent = _capture(monkeypatch)
    asyncio.run(sched.publish_curriculum_parts())
    assert NEW not in [chat for chat, _ in sent]


def test_task_turns_on_with_first_lecture_that_has_letters(test_db, monkeypatch):
    old, new = _groups()
    _parts()
    cur.backfill()
    cur.announce_start(new["id"], "j", today="2026-10-01")
    monkeypatch.setattr(cur, "get_date", lambda: "2026-10-08")
    sent = _capture(monkeypatch)
    for _ in range(3):                                    # Введение, Сколько..., Горло
        asyncio.run(sched.publish_curriculum_parts())
    assert "j" in db.get_group_tasks(db.get_group(NEW))
    told = [text for chat, text in sent if chat == NEW and "в заданиях группы" in text]
    assert len(told) == 1
    asyncio.run(sched.publish_curriculum_parts())         # дальше - без повторного объявления
    assert len([t for c, t in sent if c == NEW and "в заданиях группы" in t]) == 1


def test_student_sees_lessons_of_his_group_only(test_db):
    from core.lessons import lesson, lessons_of
    old, new = _groups()
    _parts()
    cur.backfill()
    db.add_student("Сатар", new["id"], phone="555001")
    with db.db() as c:
        first = c.execute("SELECT id FROM curriculum_parts ORDER BY order_index LIMIT 1").fetchone()["id"]
    gid = cur.user_group_id("555001")
    assert gid == new["id"]
    assert lesson(first, gid) is None                     # группе ещё не открыт
    assert lesson(first, old["id"])["topic"] == "Введение"
    cur.open_part(new["id"], first)
    assert lesson(first, gid)["topic"] == "Введение"
    assert [x["open"] for x in lessons_of("j", gid)] == [True, False, False, False]


def test_readiness_counts_all_students_and_waits_for_the_date(test_db, monkeypatch):
    old, new = _groups()
    for i in range(10):
        db.add_student("С%d" % i, new["id"], phone="56%04d" % i)
    pages = {"56%04d" % i: 12 for i in range(7)}           # 7 из 10 прошли полджуза
    pages["560007"] = 5                                     # у двоих указателя нет вовсе
    _pointers(monkeypatch, pages)
    stats = cur.readiness(new["id"])
    assert (stats["total"], stats["with_pointer"], stats["j"], stats["n"]) == (10, 8, 7, 0)
    assert cur.is_ready(stats, "j") and not cur.is_ready(stats, "n")

    sent = _capture(monkeypatch)
    monkeypatch.setattr(sched, "get_date", lambda: "2026-09-20")    # до AUTO_OPEN_FROM - тишина
    asyncio.run(sched.subject_readiness_check())
    assert sent == []

    monkeypatch.setattr(sched, "get_date", lambda: "2026-10-01")    # четверг
    asyncio.run(sched.subject_readiness_check())
    to_group = [t for c, t in sent if c == NEW]
    assert len(to_group) == 1 and "08.10" in to_group[0] and "таджвид" in to_group[0]
    assert cur.subject_start(new["id"], "j")["start_date"] == "2026-10-08"
    asyncio.run(sched.subject_readiness_check())                    # второй раз не объявляем
    assert len([t for c, t in sent if c == NEW]) == 1


def test_share_below_threshold_does_not_open(test_db, monkeypatch):
    old, new = _groups()
    for i in range(10):
        db.add_student("С%d" % i, new["id"], phone="57%04d" % i)
    _pointers(monkeypatch, {"57%04d" % i: 30 for i in range(6)})    # 60%
    assert not cur.is_ready(cur.readiness(new["id"]), "j")


def test_first_lesson_is_thursday_at_least_a_week_away():
    assert cur.first_lesson_date("2026-10-01") == "2026-10-08"      # чт -> следующий чт
    assert cur.first_lesson_date("2026-10-02") == "2026-10-15"      # пт -> через чт
