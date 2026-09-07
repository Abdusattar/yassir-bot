"""Очередь учебной программы (нахв/таджвид) — публикация по четвергам.

Живой пропуск 07.09.2026: нахв не уходил в группы три четверга подряд
(20.08, 27.08, 03.09), а женская база — где очередь СВОЯ и кончилась
раньше — стояла с 13.08. Никто этого не заметил, потому что пустая очередь
была тихим no-op: предупреждение приходило ровно один раз, когда оставалась
последняя часть, и больше бот не напоминал никогда.
"""

import asyncio

import core.db as db
import core.scheduler as sched


CHAT = "-100777001"


def _group_with_nahw():
    db.save_group(CHAT, "N-1", tasks="m,r,t,n")
    return db.get_group(CHAT)


def _capture(monkeypatch, admin="900001"):
    sent = []

    async def fake_send_message(chat_id, text, reply_to_message_id=None):
        sent.append((str(chat_id), text))

    monkeypatch.setattr(sched, "send_message", fake_send_message)
    monkeypatch.setattr(sched, "SUPER_ADMIN_IDS", [admin])
    return sent


def test_empty_queue_tells_the_admin_instead_of_silence(test_db, monkeypatch):
    """Главное, ради чего заведён файл: пустой четверг не должен молчать."""
    _group_with_nahw()
    sent = _capture(monkeypatch)

    asyncio.run(sched.publish_curriculum_parts())

    to_group = [s for s in sent if s[0] == CHAT]
    to_admin = [s for s in sent if s[0] == "900001"]
    assert to_group == []                       # в группы по-прежнему ничего
    assert len(to_admin) == 2                   # по одному на нахв и таджвид
    assert "очередь пуста" in to_admin[0][1]


def test_part_goes_to_groups_with_that_task_only(test_db, monkeypatch):
    """Урок нахва уходит в группу с заданием «n» и не уходит в остальные."""
    _group_with_nahw()
    db.save_group("-100777002", "G-9", tasks="m,r,t")     # без нахва
    sent = _capture(monkeypatch)
    db.save_curriculum_part("n", "الكلمة", "الجمع وأنواعه", 1, 4, 6, "текст урока")

    asyncio.run(sched.publish_curriculum_parts())

    chats = [s[0] for s in sent]
    assert CHAT in chats
    assert "-100777002" not in chats
    assert "текст урока" in dict(sent)[CHAT]


def test_published_part_does_not_go_out_twice(test_db, monkeypatch):
    """Вторая публикация подряд не должна повторять ту же часть — иначе
    сбой планировщика превратился бы в дубль в группе."""
    _group_with_nahw()
    _capture(monkeypatch)
    db.save_curriculum_part("n", "الكلمة", "الجمع وأنواعه", 1, 4, 6, "текст урока")

    asyncio.run(sched.publish_curriculum_parts())
    assert db.count_unpublished_parts("n") == 0

    sent = _capture(monkeypatch)
    asyncio.run(sched.publish_curriculum_parts())
    assert [s for s in sent if s[0] == CHAT] == []


def test_last_part_still_warns_a_week_ahead(test_db, monkeypatch):
    """Старое предупреждение (23.07.2026) осталось живым: когда ушла
    предпоследняя часть, устазу приходит «остался 1 урок»."""
    _group_with_nahw()
    sent = _capture(monkeypatch)
    db.save_curriculum_part("n", "الكلمة", "тема 1", 1, 2, 6, "первая")
    db.save_curriculum_part("n", "الكلمة", "тема 2", 2, 2, 7, "вторая")

    asyncio.run(sched.publish_curriculum_parts())

    warnings = [t for c, t in sent if c == "900001" and "остался всего 1 урок" in t]
    assert len(warnings) == 1
